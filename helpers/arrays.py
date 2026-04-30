def is_matrix(mat):
    if not isinstance(mat, list):
        return False
    if not all(isinstance(row, (list, tuple, set)) for row in mat):
        return False
    if len(mat) == 0:
        return False
    if not all(len(row) == len(mat[0]) for row in mat):
        return False
    return True
