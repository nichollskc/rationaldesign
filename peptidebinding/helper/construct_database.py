"""Constructs database of interacting fragments."""
import logging

import numpy as np
import pandas as pd

import peptidebinding.helper.distances as distances
import peptidebinding.helper.utils as utils


def read_matrix_from_file(pdb_id):
    """Reads interaction matrix from file and return as np.array.

    Args:
        pdb_id (string): string of PDB ID e.g. "2zxx".

    Returns:
        np.array: interaction matrix as an np.array
    """
    ids_filename = utils.get_id_filename(pdb_id)
    matrix_filename = utils.get_matrix_filename(pdb_id)

    # Read in residue IDs
    ids = pd.read_csv(ids_filename, sep=" ", header=None)
    num_residues = ids.shape[0]

    # Read in binary matrix
    with open(matrix_filename, 'rb') as f:
        raw = np.fromfile(f, np.int32)

    # Found dimensions from corresponding ids.txt file
    matrix = raw.reshape((num_residues, num_residues))

    return matrix


def read_matrix_from_file_df(pdb_id):
    """Read interaction matrix from file, label using IDs file and return as a
    data frame.

    Args:
        pdb_id (string): string of PDB ID e.g. "2zxx".

    Returns:
        pd.DataFrame: data frame containing the matrix, with labels given by
            the rows of the IDs file
    """
    matrix = read_matrix_from_file(pdb_id)
    ids_filename = utils.get_id_filename(pdb_id)

    # Combine the three columns into one label for each residue
    ids = pd.read_csv(ids_filename, sep=" ", header=None)
    combined_labels = ids.apply(lambda x: '_'.join(x.map(str)), axis=1)

    df = pd.DataFrame(matrix, index=combined_labels, columns=combined_labels)
    return df


def find_target_indices_from_matrix(matrix, cdr_indices):
    """
    Finds all indices that interact with the given CDR according to the matrix.

    Args:
        matrix (np.array): square matrix giving interactions between residues,
            described further in find_all_binding_pairs_indices.
        cdr_indices (array): array of indices for which we want to find
            interactions.

    Returns:
        array: array of indices that interact with any of the indices of CDR.
    """
    target_indices_np = ((matrix.iloc[cdr_indices, :] < 0).sum(axis=0) > 0).to_numpy().nonzero()
    target_indices = list(target_indices_np[0])

    for index in cdr_indices:
        if index in target_indices:
            target_indices.remove(index)

    return target_indices


def combine_bound_pairs(filename_list):
    """Read in all the bound pairs from the csv files in `filename_list` and
    combine them into a single dataframe"""
    data_frames = [utils.read_bound_pairs(filename) for filename in filename_list]
    combined_data_frame = pd.concat(data_frames)
    return combined_data_frame


def remove_duplicate_rows(data_frame, columns):
    """
    Removes rows from the data frame if the values in all columns specified are the same.
    The first duplicate of each set will be removed.

    Args:
        data_frame (pandas.DataFrame): data frame
        columns (array): array of column names e.g. ['cdr_residues', 'target_residues']
            rows must match on all the given columns to count as a duplicate

    Returns:
        pandas.DataFrame: data frame which is a copy of the original but with
            duplicated rows removed.
    """
    logging.info(f"Removing duplicates from dataframe with {len(data_frame)} rows, "
                 f"based on the columns {columns}.")
    row_is_duplicate = data_frame.duplicated(columns, keep='first')
    no_duplicates = data_frame[~ row_is_duplicate]
    logging.info(f"After removing duplicates based on columns {columns}, data frame "
                 f"now has {len(no_duplicates)} rows.")

    return no_duplicates


def generate_proposal_negatives(data_frame, k):
    """Given a data frame, shuffle and pair the rows to produce a set of k proposal
    negative examples. Return these in a data frame."""
    logging.info(f"Generating {k} negatives for data frame of length {len(data_frame)}")

    proposals_df = data_frame.sample(n=k, replace=True).reset_index(drop=True).join(
        data_frame.sample(n=k, replace=True).reset_index(drop=True),
        rsuffix="_donor")

    logging.info(f"Updating column values for these proposals")
    proposals_df['original_cdr_bp_id_str'] = proposals_df['cdr_bp_id_str']
    proposals_df['original_cdr_resnames'] = proposals_df['cdr_resnames']
    proposals_df['original_cdr_pdb_id'] = proposals_df['cdr_pdb_id']

    proposals_df['cdr_bp_id_str'] = proposals_df['cdr_bp_id_str_donor']
    proposals_df['cdr_resnames'] = proposals_df['cdr_resnames_donor']
    proposals_df['cdr_pdb_id'] = proposals_df['cdr_pdb_id_donor']

    proposals_df['binding_observed'] = 0

    proposals_df['paired'] = list(zip(proposals_df['cdr_resnames'],
                                      proposals_df['target_resnames']))

    logging.info(f"Updated column values for these proposals")

    return proposals_df


def remove_invalid_negatives(combined_df):
    """Finds similarity between the rows that have been combined to form negatives
    and removes any that are formed by rows that are too similar. Judged by
    sequence alignment between CDRs and targets."""
    new_negatives_rows = (combined_df['binding_observed'] == 0) & \
                         (np.isnan(combined_df['similarity_score']))
    logging.info(f"Verifying {(new_negatives_rows).sum()} new negatives")

    cdr_scores = distances.calculate_alignment_scores(combined_df.loc[new_negatives_rows,
                                                                      'cdr_resnames'],
                                                      combined_df.loc[new_negatives_rows,
                                                                      'original_cdr_resnames'])
    target_scores = distances.calculate_alignment_scores(combined_df.loc[new_negatives_rows,
                                                                         'target_resnames'],
                                                         combined_df.loc[new_negatives_rows,
                                                                         'target_resnames_donor'])

    logging.info(f"Computed scores")
    total_scores = [sum(scores) for scores in zip(cdr_scores, target_scores)]
    combined_df.loc[new_negatives_rows, 'similarity_score'] = total_scores

    too_similar_indices = combined_df.index[(combined_df['similarity_score'] >= 0)]
    logging.info(f"Rejected {len(too_similar_indices)} rows for being too similar")
    combined_df = combined_df.drop(too_similar_indices, axis=0)
    return combined_df


def generate_negatives_alignment_threshold(bound_pairs_df, k=None, seed=42):
    """Given a data frame consisting of bound pairs (i.e. positive examples of
    binding), return a copy with extra rows corresponding to negative examples.
    Negatives are formed by exchanging the CDR of one row for the CDR of another,
    and are marked by the `binding_observed` column being zero. The details of
    the original CDR that has been replaced will be included in the column.

    If (C,T) and (c,t) are two bound pairs, then we can generate a negative
    (C,t) as long as distance(C,c) and distance(T,t) are both sufficiently large.
    In this case distance is measured by sequence alignment.

    This negative will have:
    binding_observed = 0
    cdr = C
    target = t
    original_cdr = c

    Positives will have:
    binding_observed = 1
    cdr = C
    target = T
    original_cdr = NaN

    For each of cdr, target and original_cdr there are fields for PDB id, biopython
    ID string and resnames.
    """
    np.random.seed(seed)

    positives_df = bound_pairs_df.copy()
    positives_df['cdr_pdb_id'] = positives_df['pdb_id']
    positives_df['target_pdb_id'] = positives_df['pdb_id']
    positives_df = positives_df.drop(columns='pdb_id')
    positives_df['binding_observed'] = 1
    positives_df['similarity_score'] = np.nan

    considered_pairs = {x for x in zip(positives_df['cdr_resnames'],
                                       positives_df['target_resnames'])}

    negatives_dfs_arr = []
    num_negatives_produced = 0
    num_rounds = 0

    if k is None:
        k = len(bound_pairs_df.index)

    logging.info(f"Generating {k} negative examples for dataset "
                 f"containing {len(bound_pairs_df.index)} positive examples.")

    while num_negatives_produced < k:
        # Generate proposals which might be negative - by shuffling two versions of
        #   the positives data frame
        # Usually requires about 3 * k attempts to get k negatives, but we should limit to
        #   batches of 20000 to avoid issues with the command line tools
        num_proposals = min(3 * k, 1000000)
        logging.info("Generating new proposals")
        proposals_df = generate_proposal_negatives(positives_df, num_proposals)

        # Remove rows that are duplicated in the proposals
        logging.info("Removing duplicated proposals")
        proposals_df = remove_duplicate_rows(proposals_df,
                                             ['cdr_resnames', 'target_resnames'])

        # Remove proposals that have already been considered, or are existing rows in the
        #   postives data frame
        logging.info(f"Removing proposals already considered. "
                     f"Starting with {len(proposals_df)} rows.")
        proposals_df = proposals_df[~ proposals_df['paired'].isin(considered_pairs)]
        logging.info(f"After removing proposals already considered, there are "
                     f"{len(proposals_df)} rows.")

        # Add these proposals to considered pairs so we don't check them again later
        logging.info(f"Adding these {len(proposals_df)} proposals to considered list, "
                     f"to allow checking in next round.")
        considered_pairs.update(proposals_df['paired'])

        # Perform alignment for these proposals and check they are reasonable negatives
        logging.info("Removing invalid negatives based on alignment")
        negatives_df = remove_invalid_negatives(proposals_df)

        num_negatives_produced += len(negatives_df)
        negatives_dfs_arr.append(negatives_df)

        logging.info(f"Progress: {num_negatives_produced/k:.2%}. "
                     f"Generated {num_negatives_produced} negatives so far.")

        if num_rounds % 10 == 0:
            filename = f".tmp.negatives_df_{num_negatives_produced}.csv"
            logging.info(f"Saving data frame so far to file {filename}: "
                         f"concatenating {len(negatives_dfs_arr)} data frames.")
            # Save the data frame as a checkpoint
            combined_df = pd.concat(negatives_dfs_arr, sort=False).reset_index(
                drop=True)
            logging.info(f"Saving data frame so far to file {filename}: saving to file.")
            combined_df.to_csv(filename)
            logging.info("Saved to file.")

        num_rounds += 1

    logging.info(f"Concatenating all negatives with the positives into a new data frame. "
                 f"There are {len(negatives_dfs_arr)} data frames containing negatives.")
    combined_df = pd.concat([positives_df] + negatives_dfs_arr, sort=False).reset_index(drop=True)

    logging.info(f"Generated {num_negatives_produced} negative samples. Required "
                 f"{k} negatives. Will trim "
                 f"{num_negatives_produced - k} rows from the negatives.")
    combined_df = combined_df.iloc[:len(positives_df) + k, :]

    good_cols = [col for col in combined_df.columns if not col.endswith('donor')]
    combined_df = combined_df[good_cols]

    return combined_df


def split_dataset_random(data_frame, group_proportions, seed=42):
    """Splits the rows of a data frame randomly into groups according to the group
    proportions. Group proportions should be a list e.g. [60, 20, 20]."""
    # np.split requires a list of cummulative fractions for the groups
    #   e.g. [60, 20, 20] -> [0.6, 0.2, 0.2] -> [0.6, 0.6 + 0.2] = [0.6, 0.8]
    fractions = np.cumsum([group_proportions])[:-1] / sum(group_proportions)

    logging.info(f"Intended fractions are {fractions}")
    counts = list(map(int, (fractions * len(data_frame))))
    logging.info(f"Intended counts per group are {counts}")
    grouped_dfs = np.split(data_frame.sample(frac=1, random_state=seed), counts)

    return grouped_dfs
