import theano
import numpy
import math
from theano import gof, tensor, function, scalar
from theano.sandbox.linalg.ops import diag
from theano.tests import unittest_tools as utt


class Fourier(gof.Op):
    """
    An instance of this class returns a finite fourier transform calcutated
    along one dimension of an input array.

    inputs:

    a : Array of at least one dimension.  Can be complex.
    n : Integer, optional. Length of the transformed axis of the output. If n
    is smaller than the length of the input, the input is cropped. If it is
    larger, the input is padded with zeros. If n is not given, the length of
    the input (along the axis specified by axis) is used.
    axis : Integer, optional. Axis over which to compute the FFT. If not
    supplied, the last axis is used.

    output:

    Complex array.  The input array, transformed along the axis
    indicated by 'axis' or along the last axis if 'axis' is not specified. It
    is truncated or zero-padded as required if 'n' is specified.
    (From numpy.fft.fft's documentation:)
    The values in the output follow so-called standard order. If A = fft(a, n),
    then A[0] contains the zero-frequency term (the mean of the signal), which
    is always purely real for real inputs. Then A[1:n/2] contains the
    positive-frequency terms, and A[n/2+1:] contains the negative-frequency
    terms, in order of decreasingly negative frequency. For an even number of
    input points, A[n/2] represents both positive and negative Nyquist
    frequency, and is also purely real for real input. For an odd number of
    input points, A[(n-1)/2] contains the largest positive frequency, while
    A[(n+1)/2] contains the largest negative frequency.
    """

    def __eq__(self, other):
        return type(self) == type(other)

    def __hash__(self):
        return hash(self.__class__)

    def __str__(self):
        return self.__class__.__name__

    def make_node(self, a, n, axis):
        a = tensor.as_tensor_variable(a)
        if a.ndim < 1:
            raise TypeError('%s: input must be an array, not a scalar' %
                            self.__class__.__name__)
        if axis is None:
            axis = a.ndim - 1
            axis = tensor.as_tensor_variable(axis)
        else:
            axis = tensor.as_tensor_variable(axis)
            if (not axis.dtype.startswith('int')) and \
               (not axis.dtype.startswith('uint')):
                raise TypeError('%s: index of the transformed axis must be'
                                ' of type integer' % self.__class__.__name__)
            elif axis.ndim != 0 or (isinstance(axis, tensor.TensorConstant) and
                                    (axis.data < 0 or axis.data > a.ndim - 1)):
                raise TypeError('%s: index of the transformed axis must be'
                                ' a scalar not smaller than 0 and smaller than'
                                ' dimension of array' % self.__class__.__name__)

        if n is None:
            n = a.shape[axis]
            n = tensor.as_tensor_variable(n)
        else:
            n = tensor.as_tensor_variable(n)
            if (not n.dtype.startswith('int')) and \
               (not n.dtype.startswith('uint')):
                raise TypeError('%s: length of the transformed axis must be'
                                ' of type integer' % self.__class__.__name__)
            elif n.ndim != 0 or (isinstance(n, tensor.TensorConstant) and
                                 n.data < 1):
                raise TypeError('%s: length of the transformed axis must be a'
                                ' strictly positive scalar'
                                % self.__class__.__name__)

        return gof.Apply(self, [a, n, axis], [tensor.TensorType('complex128',
                        a.type.broadcastable)()])

    def infer_shape(self, node, in_shapes):
        shape_a = in_shapes[0]
        n = node.inputs[1]
        axis = node.inputs[2]
        if len(shape_a) == 1:
            return (shape_a,)
        elif isinstance(axis, tensor.TensorConstant):
            out_shape = list(shape_a[0: axis.data]) + [n] + list(shape_a[axis.data + 1:])
        else:
            l = len(shape_a)
            shape_a = tensor.stack(*shape_a)
            out_shape = tensor.concatenate((shape_a[0: axis], [n],
                                            shape_a[axis + 1:]))
            n_splits = [1] * l
            out_shape = tensor.split(out_shape, n_splits, l)
            out_shape = [a[0] for a in out_shape]
        return [out_shape]

    def perform(self, node, inputs, output_storage):
        a = inputs[0]
        n = inputs[1]
        axis = inputs[2]
        output_storage[0][0] = numpy.fft.fft(a, n=int(n), axis=axis)

    def grad(self, inputs, cost_grad):
        """
        In defining the gradient, the Finite Fourier Transform is viewed as
        a complex-differentiable function of a complex variable
        """
        a = inputs[0]
        n = inputs[1]
        axis = inputs[2]
        grad = cost_grad[0]
        if not isinstance(axis, tensor.TensorConstant):
            raise NotImplementedError('%s: gradient is currently implemented'
                                      ' only for axis being a Theano constant'
                                      % self.__class__.__name__)
        axis = int(axis.data)

        # notice that the number of actual elements in wrto is independent of
        # possible padding or truncation:
        ele = tensor.arange(0, tensor.shape(a)[axis], 1)
        outer = tensor.outer(ele, ele)
        pow_outer = tensor.exp(((-2 * math.pi * 1j) * outer) / (1. * n))
        res = tensor.tensordot(grad, pow_outer, (axis, 0))
        return [res, None, None]

fft = Fourier()


import numpy
from theano import tensor, function, scalar
from theano.sandbox.linalg.ops import diag
from theano.tests import unittest_tools as utt
#from theano import Fourier fft


class TestFourier(utt.InferShapeTester):

    rng = numpy.random.RandomState(43)

    def setUp(self):
        super(TestFourier, self).setUp()
        self.op_class = Fourier
        self.op = fft

    def test_perform(self):
        a = tensor.dmatrix()
        f = function([a], self.op(a, n=10, axis=0))
        a = numpy.random.rand(8, 6)
        assert numpy.allclose(f(a), numpy.fft.fft(a))

    def test_infer_shape(self):
        a = tensor.dvector()
        self._compile_and_check([a], [self.op(a, 16, 0)],
                                [numpy.random.rand(12)],
                               self.op_class)
        a = tensor.dmatrix()
        for var in [self.op(a, 16, 1), self.op(a, None, 1),
                     self.op(a, 16, None), self.op(a, None, None)]:
            self._compile_and_check([a], [var],
                                    [numpy.random.rand(12, 4)],
                                    self.op_class)
        b = tensor.iscalar()
        for var in [self.op(a, 16, b), self.op(a, None, b)]:
            self._compile_and_check([a, b], [var],
                                    [numpy.random.rand(12, 4), 0],
                                    self.op_class)

    def test_gradient(self):
            def fft_test1(a):
                return self.op(a, 8, 1)

            def fft_test2(a):
                return self.op(a, None, 1)

            def fft_test3(a):
                return self.op(a, None, None)

            def fft_test4(a):
                return self.op(a, 3, None)

            pts = [numpy.random.rand(2, 5, 4, 3),
                   numpy.random.rand(2, 5, 4),
                   numpy.random.rand(2, 5),
                   numpy.random.rand(5)]
            for fft_test in [fft_test1, fft_test2, fft_test3, fft_test4]:
                for pt in pts:
                    theano.gradient.verify_grad(fft_test, [pt],
                                                n_tests=1, rng=TestFourier.rng,
                                                out_type='complex64')


if __name__ == "__main__":
    t = TestFourier('setUp')
    t.setUp()
    t.test_perform()
    t.test_infer_shape()
    t.test_gradient()
