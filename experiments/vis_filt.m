function vis_filt(fn)

load(fn);

W = Ws{end};
W = permute(W, [3, 4, 2, 1]);

M = max(abs(W),[],1); M = max(M,[],2); M = max(M,[],3);
W = bsxfun(@rdivide, W, M);

W = (W + 1)/2;

montage(W, 'size', [1 NaN]);
imwrite(getimage(gca), [fn '.png']);