import argparse
import logging

import Bio.PDB

import scripts.helper.log_utils as log_utils
import scripts.helper.query_biopython as bio
import scripts.helper.utils as utils


def write_bound_pair_to_pdb(row):
    """Generate a pdb file for the given bound pair, superimposing the CDRs
    if the pair was generated by permutation.

    Returns filename where bound pair was written.

    If the pair is a positive, we simply extract the residues of the CDR and
    target and write to file.

    If the pair is a generated negative then we will have an original CDR and
    a new CDR. We calculate the mapping that would take the alpha carbons of the
    new CDR to the locations of the alpha carbons of the original CDR and then
    apply this mapping to all the atoms in the new CDR.
    We then write this newly mapped CDR and the target to file.

    The file will have a name that uniquely identifies the bound pair, given by
    utils.get_bound_pair_id_from_row"""
    cdr_struct = Bio.PDB.PDBParser().get_structure(row['cdr_pdb_id'],
                                                   utils.get_pdb_filename(row['cdr_pdb_id']))
    cdr = bio.select_residues_from_compact_bp_id_string(row['cdr_bp_id_str'],
                                                        cdr_struct)

    target_struct = Bio.PDB.PDBParser().get_structure(row['target_pdb_id'],
                                                      utils.get_pdb_filename(row['target_pdb_id']))
    target = bio.select_residues_from_compact_bp_id_string(row['target_bp_id_str'],
                                                           target_struct)

    # If this is a negative example, map the new CDR onto the original CDR
    if row['binding_observed'] == 0:
        original_cdr = bio.select_residues_from_compact_bp_id_string(row['original_cdr_bp_id_str'],
                                                                     target_struct)

        sup = Bio.PDB.Superimposer()
        fixed = [res['CA'] for res in original_cdr]
        moving = [res['CA'] for res in cdr]
        sup.set_atoms(fixed, moving)
        for res in cdr:
            sup.apply(res)

    # Construct a structure containing all the residues to be saved
    s = Bio.PDB.Structure.Structure('pair')
    m = Bio.PDB.Model.Model(0)
    s.add(m)
    cdr_chain = Bio.PDB.Chain.Chain('C')
    target_chain = Bio.PDB.Chain.Chain('T')

    for res in cdr:
        cdr_chain.add(res)

    for res in target:
        target_chain.add(res)

    m.add(cdr_chain)
    m.add(target_chain)

    # Save the structure
    bound_pair_id = utils.get_bound_pair_id_from_row(row)
    filename = f"processed/pdbs/{bound_pair_id}.pdb"
    bio.save_structure(s, filename)

    return filename


def write_bound_pair_to_pdb_wrapped(bound_pair_id):
    row_dict = utils.get_dict_from_bound_pair_id(bound_pair_id)
    write_bound_pair_to_pdb(row_dict)


def write_all_bound_pairs_pdb(bound_pairs_df):
    """Write every row in the data frame to a PDB file, as in write_bound_pair_to_pdb.
    Returns a list of all the files written."""
    filenames = []
    for ind, row in bound_pairs_df.iterrows():
        filename = write_bound_pair_to_pdb(row)
        filenames.append(filename)

        if len(filenames) % 10:
            logging.info(f"Saved {len(filenames)} PDB files so far, last was {filename}")

    return filenames


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate a pdb file for each bound pair in a table, superimposing the CDRs "
                    "if the pair was generated by permutation.")
    parser.add_argument("--verbosity",
                        help="verbosity level for logging",
                        default=2,
                        type=int,
                        choices=[0, 1, 2, 3, 4])

    parser.add_argument('input',
                        help="data frame containing bound pairs to write to PDB files",
                        type=argparse.FileType('r'))
    parser.add_argument('--filenames_out',
                        help="file to store names of all files written")

    args = parser.parse_args()

    log_utils.setup_logging(args.verbosity)

    filenames = write_all_bound_pairs_pdb(args.input)

    with open(args.filenames_out, 'w') as f:
        f.write("\n".join(filenames))
