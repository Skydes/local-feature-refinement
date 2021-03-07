import argparse

import os

import subprocess

import types


# Debug flag.
skip_refinement = ('SKIP_REFINEMENT' in os.environ)


# (
# maximum image edge at feature extraction octave 0,
# maximum sum of image edges at feature extraction octave 0
# )
max_size_dict = {
    'sift': (1600, 3200),
    'surf': (1600, 3200),
    'd2-net': (1600, 2800),
    'keynet': (1600, 3200),
    'r2d2': (1600, 3200),
    'superpoint': (1600, 2800),
}


# (
# type of matcher,
# matcher threshold
# )
matcher_dict = {
    'sift': ('ratio', 0.8),
    'surf': ('ratio', 0.8),
    'd2-net': ('similarity', 0.8),
    'keynet': ('ratio', 0.9),
    'r2d2': ('similarity', 0.9),
    'superpoint': ('similarity', 0.755)
}


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '--colmap_path', type=str, required=True,
        help='path to the COLMAP executable folder'
    )

    parser.add_argument(
        '--dataset_name', type=str, required=True,
        help='dataset name'
    )

    parser.add_argument(
        '--method_name', type=str, required=True,
        help='method name'
    )

    parser.add_argument(
        '--evaluation_path', type=str, required=True,
        help='path to the evaluation executable folder'
    )

    args = parser.parse_args()
    return args


if __name__ == '__main__':
    args = parse_args()

    # Check that method exists in dictionaries with constants.
    if (args.method_name not in max_size_dict) or (args.method_name not in matcher_dict):
        raise ValueError('Method \'%s\' is unknown. Make sure it was added to the dictionaries with constants.' % args.method_name)

    # Create the output folder.
    if not os.path.exists('output'):
        os.mkdir('output')

    # Define extra paths.
    paths = types.SimpleNamespace()
    paths.dataset_path = os.path.join('ETH3D', args.dataset_name)
    paths.scan_file = os.path.join(paths.dataset_path, 'dslr_scan_eval', 'scan_alignment.mlp')
    paths.image_path = os.path.join(paths.dataset_path, 'images')
    paths.match_list_file = os.path.join(paths.dataset_path, 'match-list.txt')
    paths.matches_file = os.path.join('output', '%s-%s-matches.pb' % (args.method_name, args.dataset_name))
    paths.solution_file = os.path.join('output', '%s-%s-solution.pb' % (args.method_name, args.dataset_name))
    paths.ref_ply_file = os.path.join(paths.dataset_path, 'sparse-%s-ref.ply' % args.method_name)
    paths.raw_ply_file = os.path.join(paths.dataset_path, 'sparse-%s-raw.ply' % args.method_name)
    paths.ref_results_file = os.path.join('output', '%s-%s-ref.txt' % (args.method_name, args.dataset_name))
    paths.raw_results_file = os.path.join('output', '%s-%s-raw.txt' % (args.method_name, args.dataset_name))

    # Compute the tentative matches graph and the two-view patch geometry estimates.
    if not os.path.exists(paths.matches_file):
        subprocess.call([
            'python', 'two-view-refinement/compute_match_graph.py',
            '--method_name', args.method_name,
            '--max_edge', str(max_size_dict[args.method_name][0]),
            '--max_sum_edges', str(max_size_dict[args.method_name][1]),
            '--image_path', paths.image_path,
            '--match_list_file', paths.match_list_file,
            '--matcher', matcher_dict[args.method_name][0],
            '--threshold', str(matcher_dict[args.method_name][1]),
            '--output_file', paths.matches_file
        ])

    # Run the multi-view optimization.
    if not skip_refinement:
        subprocess.call([
            'multi-view-refinement/build/solve',
            '--matches_file', paths.matches_file,
            '--output_file', paths.solution_file
        ])

    # Run reconstruction for refined features.
    if not skip_refinement:
        subprocess.call([
            'python', 'reconstruction-scripts/triangulation_pipeline.py',
            '--colmap_path', args.colmap_path,
            '--dataset_path', paths.dataset_path,
            '--method_name', args.method_name,
            '--matches_file', paths.matches_file,
            '--solution_file', paths.solution_file
        ])

    # Run reconstruction for raw features (without refinement).
    subprocess.call([
        'python', 'reconstruction-scripts/triangulation_pipeline.py',
        '--colmap_path', args.colmap_path,
        '--dataset_path', paths.dataset_path,
        '--method_name', args.method_name,
        '--matches_file', paths.matches_file
    ])

    # Evaluate.
    if not skip_refinement:
        with open(paths.ref_results_file, 'w') as output_file:
            subprocess.call([
                os.path.join(args.evaluation_path, 'ETH3DMultiViewEvaluation'),
                '--reconstruction_ply_path', paths.ref_ply_file,
                '--ground_truth_mlp_path', paths.scan_file,
                '--tolerances', '0.01,0.02,0.05,0.1,0.2,0.5'
            ], stdout=output_file)
    with open(paths.raw_results_file, 'w') as output_file:
        subprocess.call([
            os.path.join(args.evaluation_path, 'ETH3DMultiViewEvaluation'),
            '--reconstruction_ply_path', paths.raw_ply_file,
            '--ground_truth_mlp_path', paths.scan_file,
            '--tolerances', '0.01,0.02,0.05,0.1,0.2,0.5'
        ], stdout=output_file)
