import argparse
from pathlib import Path
import tempfile
from collections import Counter

from . import Config, log
from .score import flat_to_splits, get_flat_file, score_dataset
from .evaluate import eval_scenario, all_scenarios, main as eval_all


def _add_flag(parser, name, default=False, dest=None, help=None):
    dest = dest or name
    parser.add_argument(f'--{name}', action='store_true', default=default, help=help)
    parser.add_argument(f'--no-{name}', action='store_false', dest=name, help=help)


def parse_args():

    parser = argparse.ArgumentParser(prog='evaluate', description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-b', '--base-dir', metavar='DIR', help='mt-metrics-eval dir', type=Path, default=Path(Config.METRICS_BASE_DIR))
    parser.add_argument('-t', '--testset', help='Testset name', type=str, default='wmt22')

    subps = parser.add_subparsers(dest='subcmd', help='Sub-commands', required=True)
    validate_parser = subps.add_parser('validate', formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                       help='Validation mode: scores file is given, print only single number (accuracy). \
                                       This is useful for hyperparameter tuning. The given scores are NOT cached.')
    validate_parser.add_argument('scores', help='Scores file path', type=Path)
    validate_parser.add_argument('-w', '--width', metavar='INT', help='Digits in float after decimal point', type=int, default=6)
    validate_parser.add_argument('--pbar', help='Show progress bar', action='store_true', default=False)
    scenarios = list(all_scenarios.keys()) # + ['all']
    validate_parser.add_argument('-sc', '--scenario', choices=scenarios, help='Evaluation Scneario', type=str, default='wmt22.da_sqm_tab8')
    _add_flag(validate_parser, 'ref', default=False, help='Reference-based metric. Default is reference-free.')

    full_parser = subps.add_parser('full', formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                help='Model evaluation (full) mode. Given a model dir (e.g. marian model), score all testset systems, evaluate and show ranking. \
                                    This mode caches scores under --user-dir for subsequent use.')
    
    grp = full_parser.add_mutually_exclusive_group(required=True)
    grp.add_argument('--model', help='Model dir path. See ', type=Path)
    grp.add_argument('--scores', help='Scores file path', type=Path)
    
    full_parser.add_argument('-n', '--name', dest='metric_name', required=True,
                             help='Name for metric.')
    _add_flag(full_parser, 'ref', default=False, help='Reference-based metric. Default is reference-free.')
    full_parser.add_argument('-u', '--user-dir', metavar='DIR',
                             help='Directory for caching your own metrics', type=Path, default=Path(Config.METRICS_USER_DIR))
    full_parser.add_argument('-t', '--toolkit', 
                             help='Toolkit used for trainin the model. only valid if --model arg is given and ignored for --scores',
                             choices=['marian', 'unbabel'], default='marian')

    report_parser = subps.add_parser('report', formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                       help="Report mode: report results for all metrics cached in --base-dir and --user-dir.")
    report_parser.add_argument('-u', '--user-dir', metavar='DIR', help='Directory when your metrics are cached',
                            type=Path, default=Path(Config.METRICS_USER_DIR))
    report_parser.add_argument('-o', '--report-file', metavar='FILE', help='Output file path', type=Path, default='results.csv')

    flatten_parser = subps.add_parser('flatten', formatter_class=argparse.RawDescriptionHelpFormatter,
                                       help="Flatten dataset into a TSV file")
    _add_flag(flatten_parser, 'ref', default=False, help='Reference-based metric. Default is reference-free.')
    fpg = flatten_parser.add_mutually_exclusive_group()
    fpg.add_argument('--human', choices=['none', 'wmt-appraise', 'wmt-z', 'wmt', 'mqm'], default=None,
                     help='Include this human scores in the output file. default="none" to not include human score')
    fpg.add_argument('-m', '--metric', help='Include this segment level metric scores in TSV. Set "?" to get all the names ', type=str, default=None)
    fpg = flatten_parser.add_mutually_exclusive_group()
    fpg.add_argument('--make-refless', help='Create refless file. valid when --human or --metric', action='store_true')
    fpg.add_argument('--scores-only', help='File with scores only (no ID or segs). valid when --human or --metric', action='store_true')
    fpg.add_argument('--table', help='Table of all metrics for all segments ', action='store_true')

    args = vars(parser.parse_args())
    return args


def validate(args):
    """Validation mode: scores file is given, print only single number (accuracy) for the given scenario."""
    scenario_name = args['scenario']
    scores_file = args['scores']
    width = args['width']
    metric_name = 'my_metric'
    testset_name = args['testset']
    metrics_base_dir = args['base_dir']
    testset_path = metrics_base_dir / f'{testset_name}'
    Config.PBAR_ENABLED = args['pbar']
    reference_based = bool(args['ref'])

    data_file = get_flat_file(testset_path, reference_based=reference_based)
    assert scores_file.exists(), f"Scores file {scores_file} does not exist"
    display_name = f'*{metric_name}' + ('' if reference_based else '[noref]')  # * => not primary metric
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_folder = Path(tmp_dir) / testset_name
        log.info(f"Writing to {out_folder}")
        flat_to_splits(data_file=data_file, scores_file=scores_file, output_folder=out_folder, metric_name=metric_name)
        metrics_paths = [args['base_dir'], tmp_dir]
        if testset_name == 'toship_data':
            from .toship import main as toship_main
            res = toship_main(testset_path, metrics_paths, show_pbar=args['pbar'])
        else:
            log.info(f"Running evaluation scenario {scenario_name}")
            res = eval_scenario(paths=metrics_paths, quiet=True, scenairo_name=scenario_name)  # name: (rank, score)
        score = res[display_name][1]
        print(f'{score:.{width}f}')


def report_only(args):
    """ Produce metrics report only"""
    report_file = str(args.get('report_file', 'results.csv'))
    metrics_paths = [args['base_dir'], args['user_dir']]
    eval_all(paths=metrics_paths, out_file=report_file)

def full_eval(args):
    """ Full evaluation mode: score, evaluate and report"""
    scores_file = args.get('scores')
    testset_name = args['testset']
    metrics_base_dir = args['base_dir']
    metrics_user_dir = args['user_dir']
    testset_path = metrics_base_dir / f'{testset_name}'
    reference_based = bool(args['ref'])
    metric_name = args['metric_name']

    data_file = get_flat_file(testset_path, reference_based=reference_based)
    if not scores_file:
        model_dir = args.get('model')
        toolkit = args['toolkit']
        assert model_dir.exists(), f"Model dir {model_dir} does not exist"

        scores_file = metrics_user_dir / f'{data_file.name}.{metric_name}.seg.scores'
        score_dataset(data_file=data_file, out_file=scores_file, model_path=model_dir,
                    reference_based=reference_based, toolkit=toolkit)

    out_folder = metrics_user_dir / testset_name
    flat_to_splits(data_file=data_file, scores_file=scores_file, output_folder=out_folder, metric_name=metric_name)
    report_only(args)


def flat_file(args):
    testset_path = args['base_dir'] / args['testset']
    human_name = args['human']
    metric_name = args['metric']
    reference_based = bool(args['ref'])

    scores_only = bool(args['scores_only'])
    table_mode = bool(args['table'])

    if human_name and human_name.lower() == 'none':
        human_name = None
    data_file = get_flat_file(testset_path, reference_based=reference_based,
                              human_name=human_name, metric_name=metric_name,
                              scores_only=scores_only, table_mode=table_mode)
    print(data_file)
    if args.get('make_refless'):
        assert human_name or metric_name, "refless is valid only when --human or --metric is given"
        width = 4
        refless_file = data_file.parent / f'{data_file.stem}.refless{data_file.suffix}'
        flag_file = refless_file.with_suffix('._OK')
        if not refless_file.exists() or not flag_file.exists():
            log.info(f"Creating refless file {refless_file}")
            with open(refless_file, 'w') as out, open(data_file) as inp:
                for line in inp:
                    row = line.rstrip().split('\t')
                    assert len(row) == 7, f"Expected 7 columns, got {len(row)}: {line}"
                    # input  :: 0=langs, 1=ref_name, 2=sys_name 3=src_seg 4=ref_seg 5=hyp_seg, 6=score
                    # output ::  langs docid sysname score src_seg hyp_seg
                    score = float(row[6])
                    row2 = [row[0], "-", f"{row[1]} {row[2]}", f'{score:.{width}f}', row[3], row[5]]
                    out.write("\t".join(row2) + '\n')
            flag_file.touch()

def main():
    args = parse_args()
    subcmd = args.pop('subcmd')
    if subcmd == 'report':  # report mode: report results for all models in <base-dir> and  <user-dir>
        report_only(args)
    elif subcmd == 'full':  # full mode: model path is give; score and then evaluate
       full_eval(args)
    elif subcmd == 'validate':  # validation model: scores file is given, print only single number
        validate(args)
    elif subcmd == 'flatten':
        if args.get('metric') == "?":
            p = Path(args['base_dir']) / args['testset']
            names = (p.name.replace('.seg.score', '') for p in p.glob('metric-scores/*/*.seg.score'))
            names = set('-'.join(n.split('-')[:-1]) for n in names)
            print('\n'.join(sorted(names)))
            return
        flat_file(args)
    else:
        raise ValueError(f"Unknown subcmd {subcmd}")

if __name__ == '__main__':
    main()