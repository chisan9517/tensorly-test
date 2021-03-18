import tensorly as tl

# Author: Jean Kossaifi
#         Jeremy Cohen <jeremy.cohen@irisa.fr>
#         Axel Marmoret <axel.marmoret@inria.fr>
#         Caglayan TUna <caglayantun@gmail.com>

# License: BSD 3 clause



def soft_thresholding(tensor, threshold):
    """Soft-thresholding operator

        sign(tensor) * max[abs(tensor) - threshold, 0]

    Parameters
    ----------
    tensor : ndarray
    threshold : float or ndarray with shape tensor.shape
        * If float the threshold is applied to the whole tensor
        * If ndarray, one threshold is applied per elements, 0 values are ignored

    Returns
    -------
    ndarray
        thresholded tensor on which the operator has been applied

    Examples
    --------
    Basic shrinkage

    >>> import tensorly.backend as T
    >>> from tensorly.tenalg.proximal import soft_thresholding
    >>> tensor = tl.tensor([[1, -2, 1.5], [-4, 3, -0.5]])
    >>> soft_thresholding(tensor, 1.1)
    array([[ 0. , -0.9,  0.4],
           [-2.9,  1.9,  0. ]])


    Example with missing values

    >>> mask = tl.tensor([[0, 0, 1], [1, 0, 1]])
    >>> soft_thresholding(tensor, mask*1.1)
    array([[ 1. , -2. ,  0.4],
           [-2.9,  3. ,  0. ]])

    See also
    --------
    svd_thresholding : SVD-thresholding operator
    """
    return tl.sign(tensor)*tl.clip(tl.abs(tensor) - threshold, a_min=0)


def svd_thresholding(matrix, threshold):
    """Singular value thresholding operator

    Parameters
    ----------
    matrix : ndarray
    threshold : float

    Returns
    -------
    ndarray
        matrix on which the operator has been applied

    See also
    --------
    procrustes : procrustes operator
    """
    U, s, V = tl.partial_svd(matrix, n_eigenvecs=min(matrix.shape))
    return tl.dot(U, tl.reshape(soft_thresholding(s, threshold), (-1, 1))*V)


def procrustes(matrix):
    """Procrustes operator

    Parameters
    ----------
    matrix : ndarray

    Returns
    -------
    ndarray
        matrix on which the Procrustes operator has been applied
        has the same shape as the original tensor


    See also
    --------
    svd_thresholding : SVD-thresholding operator
    """
    U, _, V = tl.partial_svd(matrix, n_eigenvecs=min(matrix.shape))
    return tl.dot(U, V)


def hals_nnls(UtM, UtU, V=None, n_iter_max=500, tol=10e-8,
              sparsity_coefficient=None, normalize=False, nonzero_rows=False, exact=False):

    """
    Non Negative Least Squares (NNLS)

    Computes an approximate solution of a nonnegative least
    squares problem (NNLS) with an exact block-coordinate descent scheme.
    M is m by n, U is m by r, V is r by n.
    All matrices are nonnegative componentwise.

    This algorithm is defined in [1], as an accelerated version of the HALS algorithm.

    It features two accelerations: an early stop stopping criterion, and a
    complexity averaging between precomputations and loops, so as to use large
    precomputations several times.

    This function is made for being used repetively inside an
    outer-loop alternating algorithm, for instance for computing nonnegative
    matrix Factorization or tensor factorization.

    Parameters
    ----------
    UtM: r-by-n array
        Pre-computed product of the transposed of U and M, used in the update rule
    UtU: r-by-r array
        Pre-computed product of the transposed of U and U, used in the update rule
    V: r-by-n initialization matrix (mutable)
        Initialized V array
        By default, is initialized with one non-zero entry per column
        corresponding to the closest column of U of the corresponding column of M.
    n_iter_max: Postivie integer
        Upper bound on the number of iterations
        Default: 500
    tol : float in [0,1]
        early stop criterion, while err_k > delta*err_0. Set small for
        almost exact nnls solution, or larger (e.g. 1e-2) for inner loops
        of a PARAFAC computation.
        Default: 10e-8
    sparsity_coefficient: float or None
        The coefficient controling the sparisty level in the objective function.
        If set to None, the problem is solved unconstrained.
        Default: None
    nonzero_rows: boolean
        True if the lines of the V matrix can't be zero,
        False if they can be zero
        Default: False

    Returns
    -------
    V: array
        a r-by-n nonnegative matrix \approx argmin_{V >= 0} ||M-UV||_F^2
    rec_error: float
        number of loops authorized by the error stop criterion
    iteration: integer
        final number of update iteration performed
    complexity_ratio: float
        number of loops authorized by the stop criterion

    Notes
    -----
    We solve the following problem :math:`\\min_{V >= 0} ||M-UV||_F^2`

    The matrix V is updated linewise. The update rule for this resolution is::

    .. math::
        \\begin{equation}
            V[k,:]_(j+1) = V[k,:]_(j) + (UtM[k,:] - UtU[k,:]\\times V_(j))/UtU[k,k]
        \\end{equation}

    with j the update iteration.

    This problem can also be defined by adding a sparsity coefficient,
    enhancing sparsity in the solution [2]. In this sparse version, the update rule becomes::

    .. math::
        \\begin{equation}
            V[k,:]_(j+1) = V[k,:]_(j) + (UtM[k,:] - UtU[k,:]\\times V_(j) - sparsity_coefficient)/UtU[k,k]
        \\end{equation}

    References
    ----------
    .. [1]: N. Gillis and F. Glineur, Accelerated Multiplicative Updates and
       Hierarchical ALS Algorithms for Nonnegative Matrix Factorization,
       Neural Computation 24 (4): 1085-1105, 2012.

    .. [2] J. Eggert, and E. Korner. "Sparse coding and NMF."
       2004 IEEE International Joint Conference on Neural Networks
       (IEEE Cat. No. 04CH37541). Vol. 4. IEEE, 2004.

    """

    rank, n_col_M = tl.shape(UtM)
    if V is None:  # checks if V is empty
        V = tl.solve(UtU, UtM)

        V = tl.clip(V, a_min=0, a_max=None)
        # Scaling
        scale = tl.sum(UtM * V) / tl.sum(
                       UtU * tl.dot(V, tl.transpose(V)))
        V = tl.dot(scale, V)
    if exact:
        n_iter_max = 5000
        tol = 10e-12

    for iteration in range(n_iter_max):
        rec_error = 0
        rec_error0 = 0
        for k in range(rank):

            if UtU[k, k]:
                if sparsity_coefficient is not None:  # Modifying the function for sparsification

                    deltaV = tl.where((UtM[k, :] - tl.dot(UtU[k, :], V) - sparsity_coefficient) / UtU[k, k] > -V[k, :],
                                      (UtM[k, :] - tl.dot(UtU[k, :], V) - sparsity_coefficient) / UtU[k, k], -V[k, :])
                    V = tl.index_update(V, tl.index[k, :], V[k, :] + deltaV)

                else:  # without sparsity

                    deltaV = tl.where((UtM[k, :] - tl.dot(UtU[k, :], V)) / UtU[k, k] > -V[k, :],
                                      (UtM[k, :] - tl.dot(UtU[k, :], V)) / UtU[k, k], -V[k, :])
                    V = tl.index_update(V, tl.index[k, :], V[k, :] + deltaV)

                rec_error = rec_error + tl.dot(deltaV, tl.transpose(deltaV))

                # Safety procedure, if columns aren't allow to be zero
                if nonzero_rows and tl.all(V[k, :] == 0):
                    V[k, :] = tl.eps(V.dtype) * tl.max(V)

            elif nonzero_rows:
                raise ValueError("Column " + str(k) + " of U is zero with nonzero condition")

            if normalize:
                norm = tl.norm(V[k, :])
                if norm != 0:
                    V[k, :] /= norm
                else:
                    sqrt_n = 1/n_col_M ** (1/2)
                    V[k, :] = [sqrt_n for i in range(n_col_M)]
        if iteration == 1:
            rec_error0 = rec_error

        numerator = tl.shape(V)[0]*tl.shape(V)[1]+tl.shape(V)[1]*rank
        denominator = tl.shape(V)[0]*rank+tl.shape(V)[0]
        complexity_ratio = 1+(numerator/denominator)
        if exact:
            if rec_error < tol * rec_error0:
                break
        else:
            if rec_error < tol * rec_error0 or iteration > 1 + 0.5 * complexity_ratio:
                break

    return V, rec_error, iteration, complexity_ratio
    
def active_set_nnls(A, B, x=None, n_iter_max=100):
    """
    A=bx
    Parameters
    ----------
    a: Tensor
    b: list of matrices
    x: initial tensor
    n_iter_max : int
    gradient_step : float
    sparsity_coefficient :

    Returns
    -------
    x: Tensor
    """
    #For gradient
    pseudo_inverse = B.copy()
    for i, b in enumerate(B):
            pseudo_inverse[i] = tl.dot(tl.conj(tl.transpose(b)), b)
    rec_erroras = []
    AtB = tl.base.tensor_to_vec(multi_mode_dot(A, B, transpose=True))
    AtA = tl.tenalg.kronecker(pseudo_inverse)
    x_vec = tl.base.tensor_to_vec(x)

    first = AtB
    second = tl.base.tensor_to_vec(tl.tenalg.multi_mode_dot(x, pseudo_inverse, transpose=False))
    w = first - second
    P = []
    R = list(tl.arange(start=0, stop=tl.shape(w)[0], step=1))
    s = tl.zeros(tl.shape(x_vec))
    for iteration in range(n_iter_max):
        if tl.min(w) < 0:
            break
        indice = w.argmax()
        if len(P) == 0:
            P.append(indice)
            R.remove(indice)
        elif P[-1] != indice:
            P.append(indice)
            R.remove(indice)

        s[P] = tl.solve(AtA[P][:, P], AtB[P])

        # core update
        if tl.min(s[P]) <= 0:
            for i in range(len(P)):
                alpha = -tl.min(x_vec[P] / (x_vec[P] - s[P]))
                update = alpha * (s[P] - x_vec[P])
                x_vec[P] = x_vec[P] + update
                if x[P[i]] < 0:
                    R.append(P[i])
                    P.remove(P[i])
                    s[P] = tl.solve(AtA[P][:, P], AtB[P])
                    if s[R[i]] > 0:
                        x_vec[R[i]] = s[R[i]]
                    else:
                        x_vec[R[i]] = 0
                if tl.min(s[P]) > 0:
                    break
        else:
            x_vec[P] = s[P]

        # core update
        x = tl.reshape(x_vec, tl.shape(x))
        norm = tl.norm(update)

        # w update
        second = tl.base.tensor_to_vec(tl.tenalg.multi_mode_dot(x, pseudo_inverse, transpose=False))
        w = first - second

        # reconstruction error
        rec_erroras.append(norm)
        if iteration >= 1:
            rec_error_decrease = rec_erroras[-2] - rec_erroras[-1]
            if tl.all(x >= 0) or rec_error_decrease < 0:
                break
            if len(R) == 0:
                break
    return x

def fista_nnls(A, B, x=None, n_iter_max=100, gradient_step=None, sparsity_coefficient=None):
    """
    A=bx
    Parameters
    ----------
    A: Tensor
    B: list of matrices
    x: initial
    n_iter_max : int
    gradient_step
    sparsity_coefficient

    Returns
    -------
    x
    """
    if sparsity_coefficient is None:
        sparsity_coefficient = 0

    if gradient_step is None:
        gradient_step = 0.001

    if x is None:
        x=tl.zeros()

    #For gradient
    pseudo_inverse = B.copy()
    for i, b in enumerate(B):
            pseudo_inverse[i] = tl.dot(tl.conj(tl.transpose(b)), b)

    BtA = multi_mode_dot(A, B, transpose=True)

    #Parameters
    momentum_0 = 1
    norm_0 = 0
    x_upd = x


    for iteration in range(n_iter_max):
        gradient = - BtA + tl.tenalg.multi_mode_dot(x_upd, pseudo_inverse, transpose=False)
        delta_x = tl.where(gradient_step * gradient < x, gradient_step * gradient, x_upd)
        xnew = x_upd - delta_x
        momentum = (1 + np.sqrt(1 + 4 * momentum_0 ** 2)) / 2
        x_upd = xnew + ((momentum_0 - 1) / momentum) * (xnew - x)
        momentum_0 = momentum
        x= xnew
        norm = tl.norm(delta_x)
        if iteration == 1:
            norm_0 = norm
        if norm < 0.01 * norm_0:
            break
    return x
