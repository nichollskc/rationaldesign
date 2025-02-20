"""Generates representations of bound pairs for use in models.
Some code reused from these files:
https://github.com/eliberis/parapred/blob/d13600a3d5697ebd5796576e1d6166aa1a519933/parapred/data_provider.py
https://github.com/eliberis/parapred/blob/d13600a3d5697ebd5796576e1d6166aa1a519933/parapred/structure_processor.py"""
import numpy as np
import scipy.sparse
import tensorflow as tf

################################################################################
#   Utility functions                                                          #
################################################################################

residues_order = "CSTPAGNDEQHRKMILVFYWX"  # X for unknown

def resnames_to_ints(res_str):
    """Converts a string of residues e.g. 'AFFG' to an array of integers, using
    the global variable residues_order to give the order."""
    return [residues_order.index(r) for r in res_str]


# pylint: disable=bad-whitespace
def residue_features():
    """Returns a np.array with the Meiler criteria for each amino acid, with
    the order as in residues_order."""
    # Meiler's features
    prop1 = [[1.77, 0.13, 2.43,  1.54,  6.35, 0.17, 0.41],
             [1.31, 0.06, 1.60, -0.04,  5.70, 0.20, 0.28],
             [3.03, 0.11, 2.60,  0.26,  5.60, 0.21, 0.36],
             [2.67, 0.00, 2.72,  0.72,  6.80, 0.13, 0.34],
             [1.28, 0.05, 1.00,  0.31,  6.11, 0.42, 0.23],
             [0.00, 0.00, 0.00,  0.00,  6.07, 0.13, 0.15],
             [1.60, 0.13, 2.95, -0.60,  6.52, 0.21, 0.22],
             [1.60, 0.11, 2.78, -0.77,  2.95, 0.25, 0.20],
             [1.56, 0.15, 3.78, -0.64,  3.09, 0.42, 0.21],
             [1.56, 0.18, 3.95, -0.22,  5.65, 0.36, 0.25],
             [2.99, 0.23, 4.66,  0.13,  7.69, 0.27, 0.30],
             [2.34, 0.29, 6.13, -1.01, 10.74, 0.36, 0.25],
             [1.89, 0.22, 4.77, -0.99,  9.99, 0.32, 0.27],
             [2.35, 0.22, 4.43,  1.23,  5.71, 0.38, 0.32],
             [4.19, 0.19, 4.00,  1.80,  6.04, 0.30, 0.45],
             [2.59, 0.19, 4.00,  1.70,  6.04, 0.39, 0.31],
             [3.67, 0.14, 3.00,  1.22,  6.02, 0.27, 0.49],
             [2.94, 0.29, 5.89,  1.79,  5.67, 0.30, 0.38],
             [2.94, 0.30, 6.47,  0.96,  5.66, 0.25, 0.41],
             [3.21, 0.41, 8.08,  2.25,  5.94, 0.32, 0.42],
             [0.00, 0.00, 0.00,  0.00,  0.00, 0.00, 0.00]]
    return np.array(prop1)

################################################################################
#   Functions to generate flat arrays of features from raw information         #
################################################################################

def raw_onehot(resnames):
    """Generates the representation of a string of residues, where each is
    represented by an array. Each array contains the one-hot representation of
    the residue type.

    Returns an array where each row is one amino acid, and each column is a feature."""
    ints = resnames_to_ints(resnames)
    onehot = tf.keras.utils.to_categorical(ints, num_classes=len(residues_order))
    return onehot


def raw_bagofwords(resnames):
    """Generates the bag of words representation of a string of residues. Each value
    represents the number of occurrences of that amino acid in the string."""
    onehot = raw_onehot(resnames)

    return onehot.sum(axis=0).astype('int8')


def raw_crossed_bagofwords(cdr_resnames, target_resnames):
    """Return the flattened matrix where each entry (i, j) indicates the number of
    times that there is a pair (C_i, T_j) i.e. that amino acid i appears in the
    CDR and amino acid j appears in the target. Length of the array will be
    21x21=441."""
    cdr_bagofwords = raw_bagofwords(cdr_resnames)
    target_bagofwords = raw_bagofwords(target_resnames)

    return np.outer(cdr_bagofwords, target_bagofwords).flatten().astype('int8')


def raw_meiler(resnames):
    """Generates the representation of a string of residues, where each is
    represented by an array. Each array contains the 7 Meiler criteria for that residue.

    Returns an array where each row is one amino acid, and each column is a feature."""
    ints = resnames_to_ints(resnames)
    meiler = residue_features()[ints]

    return meiler


def raw_onehot_meiler(resnames):
    """Generates the representation of a string of residues, where each is
    represented by an array. The first 21 give the one-hot representation of
    the residue type and the final 7 give the Meiler criteria for that residue.

    Returns an array where each row is one amino acid, and each column is a feature."""
    meiler = raw_meiler(resnames)
    onehot = raw_onehot(resnames)

    return np.concatenate((onehot, meiler), axis=1)


def raw_padded_onehot_meiler(resnames, max_length):
    """Generate the representation as in generate_meiler_representation, but
    pad the sequence with zeros to max_length.

    Return the padded sequence and a mask indicating which are true entries and
    which are just padding."""
    num_features = len(residues_order) + 7  # one-hot + extra features

    cdr_mat = raw_onehot_meiler(resnames)
    cdr_mat_pad = np.zeros((max_length, num_features), dtype=np.float32)
    cdr_mat_pad[:cdr_mat.shape[0], :] = cdr_mat

    cdr_mask = np.zeros((max_length, 1), dtype=int)
    cdr_mask[:len(resnames), 0] = 1

    return cdr_mat_pad, cdr_mask


################################################################################
#   Functions to generate flat arrays of features for each bound pair          #
################################################################################


def generate_bagofwords(row):
    """Generates the bag of words representation of a string of residues. Each value
    represents the number of occurrences of that amino acid in the string."""
    return np.concatenate((raw_bagofwords(row['cdr_resnames']),
                           raw_bagofwords(row['target_resnames'])),
                          axis=0)


def generate_crossed_bagofwords(row):
    """Return the flattened matrix where each entry (i, j) indicates the number of
    times that there is a pair (C_i, T_j) i.e. that amino acid i appears in the
    CDR and amino acid j appears in the target. Length of the array will be
    21x21=441."""
    return raw_crossed_bagofwords(row['cdr_resnames'], row['target_resnames'])


def generate_padded_onehot_meiler(row, cdr_max_length, target_max_length):
    """Generate the representation as in generate_meiler_representation, but
    pad the sequence with zeros to max_length.

    Return the padded sequence and a mask indicating which are true entries and
    which are just padding."""
    cdr_padded, cdr_mask = raw_padded_onehot_meiler(row['cdr_resnames'],
                                                    cdr_max_length)
    target_padded, target_mask = raw_padded_onehot_meiler(row['target_resnames'],
                                                          target_max_length)

    combined_padded = np.concatenate((cdr_padded, target_padded), axis=0)
    unused_combined_mask = np.concatenate((cdr_mask, target_mask), axis=0)

    return combined_padded.flatten()


################################################################################
#   Functions to generate representations for all rows of a data frame         #
################################################################################


def generate_representation_all(bound_pairs_df, generate_func):
    """Generates the representations for all the rows of the given data frame,
    using the function generate_func to generate the representations for each
    row.

    Can give arguments for generate_func by using a lambda function e.g.
    generate_representation_all(df,
                                lambda r: generate_padded_onehot_meiler(r, 4, 12))"""
    example_rep = generate_func(bound_pairs_df.iloc[0])
    representations = scipy.sparse.lil_matrix((len(bound_pairs_df), len(example_rep)))
    for ind in range(len(bound_pairs_df)):
        representation = generate_func(bound_pairs_df.iloc[ind])
        representations[ind] = representation

    return representations
