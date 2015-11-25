from __future__ import print_function

import math, sys, time
import numpy as np
import warnings; warnings.filterwarnings("ignore")

## Load Settings

from config import *
settings = parser.parse_args(); np.random.seed(settings.seed)
# move estmem here

print('-' * 55 + ' ' + time.ctime())

## Load Network

from tools import *
net = netinit(settings.network, settings.dataset); saveW(net, settings.save)

## Load Dataset

exec 'from datasets.%s import XT, YT, Xv, Yv, Xt, Yt, NC, aug' % settings.dataset
def shuffle(X, Y): I = np.random.permutation(X.shape[0]); return X[I], Y[I]

if settings.fast:
	if len(settings.fast) < 3: XT = XT[:settings.fast[0]]; Xv = Xv[:settings.fast[0]]; Xt = Xt[:settings.fast[0]]
	else                     : XT = XT[:settings.fast[0]]; Xv = Xv[:settings.fast[1]]; Xt = Xt[:settings.fast[2]] 

if settings.noaug: aug = None

## Load Classifier

if settings.lcparam == LC_DEFAULT: settings.lcparam = LC_DEFAULT[settings.lc]

if   settings.lc == 0: from classifier.exact   import *; lcarg = ()
elif settings.lc == 1: from classifier.lowrank import *; lcarg = (settings.lcparam[0],);  settings.lcparam = settings.lcparam[1:]
else                 : from classifier.asgd    import *; lcarg = tuple(settings.lcparam); settings.lcparam = [0]

settings.peperr &= (settings.lc == 2)

if   settings.mc == 0: from classifier.formatting import ovr ; enc, dec = ovr ()
elif settings.mc == 1: from classifier.formatting import ovo ; enc, dec = ovo ()
else                 : from classifier.formatting import ecoc; enc, dec = ecoc()

## Define Epoch/Subepoch

from core.network import *

Zs = ()

#@profile
def process(X, Y, classifier, mode='train', aug=None, cp=[]):

	global Zs; smp = err = 0

	for i in xrange(0, X.shape[0], settings.batchsize):

			if not settings.quiet: t = time.time()

			Xb = X[i:i+settings.batchsize]; smp += Xb.shape[0]
			Yb = Y[i:i+settings.batchsize]

			Xb = aug(Xb) if aug is not None else Xb

			Zb = forward(net, Xb, cp)
			Zs = Zb.shape[1:]
			Zb = Zb.reshape(Zb.shape[0], -1)

			if settings.bias: Zb = np.pad(Zb, ((0,0),(0,1)), 'constant', constant_values=(1.0,))
			
			if mode == 'train': update(classifier, Zb, enc(Yb, NC)) 

			if mode == 'test'   : err += np.count_nonzero(dec(infer(classifier, Zb), NC) != Yb)
			elif settings.peperr: err += np.count_nonzero(dec(classifier.tif       , NC) != Yb)

			if not settings.quiet:
				t    = float(time.time() - t)
				msg  = 'Batch %d/%d '   % (i / float(settings.batchsize) + 1, math.ceil(X.shape[0] / float(settings.batchsize)))
				msg += '['
				#msg += 'Dim(%s) = %s; ' % ('Aug(X)' if aug is not None else 'X', str(Xb.shape[1:]))
				#msg += 'Dim(Z) = %s; '  % str(Zs)
				msg += 'ER = %e; '      % (float(err) / smp) if mode == 'train' and settings.peperr else ''
				msg += 't = %.2f Sec '  % t
				msg += '(%.2f Img/Sec)' % (Xb.shape[0] / t)
				msg += ']'
				print(msg, end='\r'); #sys.stdout.flush()

	if not settings.quiet: sys.stdout.write("\033[K") # clear line (may not be safe)
	return err

## Start

print('Start')
print('-' * 55 + ' ' + time.ctime())

## Training

classifier       = Linear(*lcarg)
CI               = [i for i in xrange(len(net)) if net[i][TYPE] == 'CONV'] # CONV layers
settings.lrnrate = evalparam(settings.lrnrate)

disable(net, 'DOUT') # disable dropout and only turn on when training CONV layers

for n in xrange(settings.epoch):

	print('Epoch %d/%d' % (n+1, settings.epoch))

	XT, YT = shuffle(XT, YT)

	for s in xrange(settings.lrnfreq):

		if len(settings.lrnrate) > 0: # Network (and Classifier) Training

			enable(net, 'DOUT')

			for l in CI[::-1]: # Top-down Order

				print('Subepoch %d/%d [Training Network Layer %d (Rate = %.2f)]' % (s+1, settings.lrnfreq, l+1, settings.lrnrate[0]))

				process(XT[s::settings.lrnfreq], YT[s::settings.lrnfreq], classifier, cp=[l], aug=aug)
				solve(classifier, settings.lcparam[-1]) # using strongest smoothing

				def unflatten(WZ): return np.rollaxis(np.reshape(WZ[:-1] if settings.bias else WZ, Zs + (-1,)), -1)

				train(net, unflatten(classifier.WZ), l, settings.lrntied, settings.lrnrate[0])
				#classifier = Linear(*lcarg) # new classifier since net changed (or not?)

			saveW(net, settings.save)
			settings.lrnrate = settings.lrnrate[1:]

			disable(net, 'DOUT')

		else: # Classifier Training

			print('Subepoch %d/%d [Training Classifier]' % (s+1, settings.lrnfreq))

			process(XT[s::settings.lrnfreq], YT[s::settings.lrnfreq], classifier, aug=aug)

	if settings.peperr and classifier.WZ is not None and n < (settings.epoch - 1):

		if Xv.shape[0] > 0: print('VAL Error = %d' % process(Xv, Yv, classifier, mode='test'))
		if Xt.shape[0] > 0: print('TST Error = %d' % process(Xt, Yt, classifier, mode='test'))

	print('-' * 55 + ' ' + time.ctime())

## Testing

for p in xrange(len(settings.lcparam)):

	print('Testing Classifier (p = %.2f)' % settings.lcparam[p])

	solve(classifier, settings.lcparam[p])

	print(                    '||WZ||    = %e' % np.linalg.norm(classifier.WZ))
	if settings.trnerr: print('TRN Error = %d' % process(XT, YT, classifier, mode='test'))
	if Xv.shape[0] > 0: print('VAL Error = %d' % process(Xv, Yv, classifier, mode='test'))
	if Xt.shape[0] > 0: print('TST Error = %d' % process(Xt, Yt, classifier, mode='test'))

	print('-' * 55 + ' ' + time.ctime())
