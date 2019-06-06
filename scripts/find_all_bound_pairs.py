"""Only works with snakemake.
Finds all CDR-like fragments and the target fragments they interact with."""
# pylint: disable=wrong-import-position
import os
import sys

sys.path.append(os.environ.get('current_dir'))

import scripts.construct_database as con_dat
import scripts.query_biopython as query_bp

# Read in parameters from snakemake
pdb_id = snakemake.params.pdb_id
fragment_length = snakemake.params.cdr_fragment_length

# Read in the matrix and find the cdrs and binding pairs within this file
matrix = con_dat.read_matrix_from_file(pdb_id)
bound_pairs, bound_pairs_fragmented = query_bp.find_all_binding_pairs(matrix,
                                                                      pdb_id,
                                                                      fragment_length)

# Output to file
con_dat.print_targets_to_file(bound_pairs,
                              snakemake.output.complete)
con_dat.print_targets_to_file(bound_pairs_fragmented,
                              snakemake.output.fragmented)
