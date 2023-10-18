#!/usr/bin/env python
import argparse
from pathlib import Path
import shutil
from typing import List
import logging as log
from collections import defaultdict
from tqdm.auto import tqdm
from . import Config


log.basicConfig(level=log.INFO)


def read_lines(filename, remove_tabs=False):
    with open(filename, "r") as f:
        lines = [line.rstrip('\n').rstrip(' ') for line in f]
    if remove_tabs:
        lines = [line.replace("\t", " ") for line in lines]
    return lines

def write_lines(path, lines):
    with open(path, "w") as f:
        f.write("\n".join(lines))

def count_lines(filename):
    with open(filename, "r") as f:
        return sum(1 for _ in f)
    
def read_tsv(filename):
    for line in read_lines(filename):
        yield line.split("\t")


def get_dataset_paths(data_folder: Path, eval_dataset=None) -> List[Path]:
    paths = []
    for dataset_path in data_folder.glob("*"):
        # check that dataset is a folder
        if not dataset_path.is_dir():
            continue

        if eval_dataset and eval_dataset != dataset_path.name:
            continue
        paths.append(dataset_path)
    return paths


def read_flat_rows(dataset_path: Path, reference_based=False):
    """
    Reads all files in dir tree as flattened rows 
    yields 6-tuple :: `(lp, ref_name, sys_name, src_seg, ref_seg, hyp_seg)`
    """
    lps = dataset_path.glob("sources/*.txt")
    # remove full path from lps
    lps = [lp.name.replace(".txt", "") for lp in lps]

    for lp in lps:
        src_segs = read_lines(dataset_path / f'sources/{lp}.txt', remove_tabs=True)
        available_refs = dataset_path.glob(f'references/{lp}*.txt')
        available_refs = [ref.name.split('.')[-2] for ref in available_refs]
        references = {}
        if not reference_based:
            # dummy references to make sure the metrics cannot see references due bug
            references['src'] = ['[NoRef]' for _ in src_segs]
        else:
            for ref_name in available_refs:
                filename = dataset_path / f"references/{lp}.{ref_name}.txt"
                if filename.exists():
                    references[ref_name] = read_lines(filename, remove_tabs=True)
                else:
                    log.warning(f"Reference {filename} does not exist")

        systems_outputs = {}
        sys_names = [sys_path.name.replace(".txt", "") for sys_path in dataset_path.glob(f"system-outputs/{lp}/*.txt")]
        for sys_name in sys_names:
            systems_outputs[sys_name] = read_lines(dataset_path / f"system-outputs/{lp}/{sys_name}.txt", remove_tabs=True)

        # score all systems across all references
        for ref_name, ref_segs in references.items():
            for sys_name, sys_segs in systems_outputs.items():
                if reference_based and sys_name == ref_name:   # skip self reference
                    continue
                assert len(src_segs) == len(ref_segs) == len(sys_segs), f'Number of segments does not match for {lp} {sys_name} {ref_name}'
                print(f"Reading {dataset_path} {lp} system: '{sys_name}' against {ref_name}")
                for _src, _ref, _hyp in zip(src_segs, ref_segs, sys_segs):
                    _hyp = _hyp  or " "
                    yield (lp, ref_name, sys_name, _src, _ref, _hyp)

def read_flat_rows_with_human(dataset_path: Path, reference_based=False, human_name='wmt-appraise'):
    """
    Reads all files in dir tree as flattened rows and their human scores
    yields 7-tuple :: `(lp, ref_name, sys_name, src_seg, ref_seg, hyp_seg, human_score)`
    """
    lps = dataset_path.glob("sources/*.txt")
    # remove full path from lps
    lps = [lp.name.replace(".txt", "") for lp in lps]

    for lp in lps:
        src_segs = read_lines(dataset_path / f'sources/{lp}.txt', remove_tabs=True)
        available_refs = dataset_path.glob(f'references/{lp}*.txt')
        human_seg_scores_file = dataset_path / f'human-scores/{lp}.{human_name}.seg.score'
        if not human_seg_scores_file.exists():
            log.warning(f"Human scores doesnt exist {human_seg_scores_file}; skipping....")
            continue
        with open(human_seg_scores_file, "r") as f:
            human_seg_scores = defaultdict(list)
            for line in f:
                row = line.strip().split('\t')
                assert len(row) == 2
                human_seg_scores[row[0]].append(row[1])

        available_refs = [ref.name.split('.')[-2] for ref in available_refs]
        references = {}
        if not reference_based:
            # dummy references to make sure the metrics cannot see references due bug
            references['src'] = ['[NoRef]' for _ in src_segs]
        else:
            for ref_name in available_refs:
                filename = dataset_path / f"references/{lp}.{ref_name}.txt"
                if filename.exists():
                    references[ref_name] = read_lines(filename, remove_tabs=True)
                else:
                    log.warning(f"Reference {filename} does not exist")

        systems_outputs = {}
        sys_names = [sys_path.name.replace(".txt", "") for sys_path in dataset_path.glob(f"system-outputs/{lp}/*.txt")]
        for sys_name in sys_names:
            systems_outputs[sys_name] = read_lines(dataset_path / f"system-outputs/{lp}/{sys_name}.txt", remove_tabs=True)

        # score all systems across all references
        stats = defaultdict(int)
        for ref_name, ref_segs in references.items():
            for sys_name, sys_segs in systems_outputs.items():
                if sys_name not in human_seg_scores:
                    log.warning(f"Human scores for {sys_name} not found in {human_seg_scores_file}")
                    continue

                human_scores = human_seg_scores[sys_name]
                assert len(src_segs) == len(ref_segs) == len(sys_segs), f'Number of segments does not match for {lp} {sys_name} {ref_name}'
                assert len(src_segs) == len(human_scores), f'Number of segments and human_scores does not match for {lp} {sys_name} {human_name}'
                print(f"Reading {dataset_path} {lp} system: '{sys_name}' against {ref_name}")
                for _src, _ref, _hyp, _hum in zip(src_segs, ref_segs, sys_segs, human_scores):
                    _hyp = _hyp  or " "
                    if _hum == 'None':
                        stats['skip_None'] += 1
                        continue
                    try:
                        float(_hum)
                    except ValueError:
                        stats['skip_non_float'] += 1
                        continue
                    stats['ok'] += 1

                    yield (lp, ref_name, sys_name, _src, _ref, _hyp, _hum)
        log.info(f"Stats: {stats}")



def read_flat_rows_with_metric(dataset_path: Path, metric_name: str, reference_based=False):
    """
    Reads all files in dir tree as flattened rows and model score
    yields 7-tuple :: `(lp, ref_name, sys_name, src_seg, ref_seg, hyp_seg, model_score)`
    """
    lps = dataset_path.glob("sources/*.txt")
    # remove full path from lps
    lps = [lp.name.replace(".txt", "") for lp in lps]

    for lp in lps:
        src_segs = read_lines(dataset_path / f'sources/{lp}.txt', remove_tabs=True)
        references = {}
        if not reference_based:
            # dummy references to make sure the metrics cannot see references due bug
            references['src'] = ['[NoRef]' for _ in src_segs]
        else:
            available_refs = dataset_path.glob(f'references/{lp}*.txt')
            available_refs = [ref.name.split('.')[-2] for ref in available_refs]
            for ref_name in available_refs:
                filename = dataset_path / f"references/{lp}.{ref_name}.txt"
                if filename.exists():
                    references[ref_name] = read_lines(filename, remove_tabs=True)
                else:
                    log.warning(f"Reference {filename} does not exist")

        systems_outputs = {}
        sys_names = [sys_path.name.replace(".txt", "") for sys_path in dataset_path.glob(f"system-outputs/{lp}/*.txt")]
        for sys_name in sys_names:
            systems_outputs[sys_name] = read_lines(dataset_path / f"system-outputs/{lp}/{sys_name}.txt", remove_tabs=True)

        # metric is scoref against a reference (e.g. refA, refB or ref); for QE models ref_name=src
        metric_scores = defaultdict(list)
        for ref_name in references:
            filename = dataset_path / f"metric-scores/{lp}/{metric_name}-{ref_name}.seg.score"
            if filename.exists():
                rows = [x.split('\t') for x in read_lines(filename)]
                for row in rows:
                    assert len(row) == 2, f"Invalid row: {row} in {filename}"
                    sys_name, score = row
                    metric_scores[(ref_name, sys_name)].append(score)
        assert metric_scores, f"No metric scores found for {metric_name} in {dataset_path}. Perhaps you messed up --ref/--no-ref option?"
        # score all systems across all references
        stats = defaultdict(int)
        metric_keys = set(metric_scores.keys())
        for ref_name, ref_segs in references.items():
            for sys_name, sys_segs in systems_outputs.items():
                if (ref_name, sys_name) not in metric_scores:
                    log.warning(f"Metric scores for {(ref_name,sys_name)} not found in {metric_keys}")
                    continue
                scores = metric_scores[(ref_name, sys_name)]
                assert len(src_segs) == len(ref_segs) == len(sys_segs), f'Number of segments does not match for {lp} {sys_name} {ref_name}'
                assert len(src_segs) == len(scores), f'Number of segments and scores does not match for {lp} {sys_name} {ref_name} {metric_name}'
                print(f"Reading {dataset_path} {lp} system: '{sys_name}' against {ref_name}")
                for _src, _ref, _hyp, _score in zip(src_segs, ref_segs, sys_segs, scores):
                    _hyp = _hyp  or " "
                    try:
                        float(_score)
                    except ValueError:
                        stats['skip_non_float'] += 1
                        continue
                    stats['ok'] += 1

                    yield (lp, ref_name, sys_name, _src, _ref, _hyp, _score)
        log.info(f"Stats: {dict(stats)}")


def read_flat_rows_with_all_metrics(dataset_path: Path, skip_self_ref=True):
    """
    Reads all files in dir tree as flattened rows and model score
    yields tuple
    """
    lps = dataset_path.glob("sources/*.txt")    # remove full path from lps
    lps = [lp.name.replace(".txt", "") for lp in lps]

    metric_names = set(x.name.replace('.seg.score', '') for x in dataset_path.glob(f"metric-scores/*/*.seg.score"))
    metric_names = [x.split('-') for x in metric_names]
    metric_names = [('-'.join(mn), rn) for *mn, rn in metric_names]
    src_based_metrics = set(mn for mn, rn in metric_names if rn == 'src')
    _metric_disp_names = {mn : f'{mn}[noref]' if rn=='src' else mn for mn, rn in metric_names}
    metric_names = [mn for mn, rn in metric_names]
    metric_names = list(sorted(set(metric_names)))
    metric_disp_names = [_metric_disp_names[mn] for mn in metric_names]

    # to get this ls  .../mt-metrics-eval-v2/wmt22/human-scores/*.seg.score | xargs -n1 basename | cut -f2 -d. | sort | uniq -c
    human_names = ['mqm', 'wmt', 'wmt-z', 'wmt-appraise', 'wmt-appraise-z']

    def clean_score(scores):
        """ replace scores that are neither float nor an explicit NA as NA"""
        res = []
        for score in scores:
            if score != 'NA':
                try:
                    float(score)
                    score = score   # valid score, keep the same string
                except ValueError:
                    score = 'NA'  # invalid score, replace with NA
            res.append(score)
        return res

    # header
    yield ('lp', 'ref_name', 'sys_name', 'src_seg', 'ref_seg', 'hyp_seg', *human_names, *metric_disp_names)

    for lp in lps:
        src_segs = read_lines(dataset_path / f'sources/{lp}.txt', remove_tabs=True)
        ref_segs = {}
        ref_names = dataset_path.glob(f'references/{lp}*.txt')
        ref_names = [ref.name.split('.')[-2] for ref in ref_names]
        for ref_name in ref_names:
            filename = dataset_path / f"references/{lp}.{ref_name}.txt"
            if filename.exists():
                ref_segs[ref_name] = read_lines(filename, remove_tabs=True)
            else:
                log.warning(f"Reference {filename} does not exist")

        systems_outputs = {}
        sys_names = [sys_path.name.replace(".txt", "") for sys_path in dataset_path.glob(f"system-outputs/{lp}/*.txt")]
        for sys_name in sys_names:
            systems_outputs[sys_name] = read_lines(dataset_path / f"system-outputs/{lp}/{sys_name}.txt", remove_tabs=True)

        human_scores = defaultdict(list)
        for human_name in human_names:
            filename = dataset_path / f"human-scores/{lp}.{human_name}.seg.score"
            if filename.exists():
                for row in read_lines(filename):
                    row = row.split('\t')
                    assert len(row) == 2, f"Invalid row: {row} in {filename}"
                    sys_name, score = row
                    human_scores[(human_name, sys_name)].append(score)
            else:
                log.warning(f"Human scores {filename} does not exist")

        # metric is scored against a reference (e.g. refA, refB or ref); for QE models ref_name=src
        metric_scores = defaultdict(list)
        for metric_name in metric_names:
            for ref_name in ref_names:
                filename = dataset_path / f"metric-scores/{lp}/{metric_name}-{ref_name}.seg.score"
                if not filename.exists() and metric_name in src_based_metrics:   # QE metric
                    filename = dataset_path / f"metric-scores/{lp}/{metric_name}-src.seg.score"
                if not filename.exists():
                    log.warning(f"Metric scores for {metric_name} not found in {dataset_path}/metric-scores/{lp}/*.txt. Skipped")
                    continue

                rows = [x.split('\t') for x in read_lines(filename)]
                for row in rows:
                    assert len(row) == 2, f"Invalid row: {row} in {filename}"
                    sys_name, score = row
                    metric_scores[(metric_name, ref_name, sys_name)].append(score)

            assert metric_scores, f"No metric scores found for {metric_name} in {dataset_path}/metric-scores/{lp}. Perhaps you messed up --ref/--no-ref option?"
        log.info(f"{lp} {len(src_segs)} src-segs {len(ref_segs)} refs {len(systems_outputs)} systems {len(human_scores)} humans {len(metric_scores)} metrics x ref")
        # score all systems across all references
        NA_SCORES = tuple(['NA' for _ in src_segs])
        # src_segs is singleton
        for ref_name, ref_segs in ref_segs.items():
            for sys_name, sys_segs in systems_outputs.items():
                if sys_name ==  ref_name and skip_self_ref:
                    continue
                assert len(src_segs) == len(ref_segs) == len(sys_segs), f'Number of segments does not match for {lp} {sys_name} {ref_name}'
                _id = (lp, ref_name, sys_name)
                _hum_scores = [human_scores.get((hn, sys_name), NA_SCORES) for hn in human_names]
                _met_scores = [metric_scores.get((mn, ref_name, sys_name), NA_SCORES) for mn in metric_names]
                # all align nicely? they should have same number of scores i.e. one per segment
                assert all(len(src_segs) == len(x) for x in _met_scores)
                assert all(len(src_segs) == len(x) for x in _hum_scores)
                _hum_scores = [clean_score(x) for x in _hum_scores]
                _met_scores = [clean_score(x) for x in _met_scores]
                for _row in zip(src_segs, ref_segs, sys_segs, *_hum_scores, *_met_scores):
                    yield (*_id, *_row)


def flat_to_splits(data_file:Path, scores_file: Path, output_folder: Path, metric_name:str):
    """Split flat scores into segment and system scores
    Args:
        data_file (Path): path to flattened data
        scores_file (Path): path to flattened scores
        output_folder (Path): where to store the results
        metric_name (str): name of the metric
    """
    score_split_ok = output_folder / (scores_file.name + "._SPLIT_OK")
    if score_split_ok.exists():
        log.info(f"Skip {score_split_ok}; data is already split")
        return
    log.info(f"Splitting {scores_file.name} into {metric_name} scores")
    seg_scores = [float(x) for x in read_lines(scores_file)]
    metas = list(r[:3] for r in read_tsv(data_file))
    assert len(seg_scores) == len(metas), \
        f"Number of scores does not match number of rows. {len(seg_scores)} != {len(metas)}"

    seg_out, sys_out = None, None
    prev_id = None
    sys_buffer = []

    def close_files():
        seg_out and seg_out.close()
        sys_out and sys_out.close()

    def reset_sys_buffer():
        """ Average segment scores as system score"""
        assert prev_id
        assert sys_buffer
        assert sys_out

        _sys_name = prev_id[2]  # (lp, ref_name, sys_name)
        _avg_score = sum(sys_buffer) / len(sys_buffer)    # mean
        sys_out.write(f"{_sys_name}\t{_avg_score}\n")
        sys_buffer.clear()

    def open_files(lp, ref_name):
        seg_score_file = output_folder / f"metric-scores/{lp}/{metric_name}-{ref_name}.seg.score"
        sys_score_file = output_folder / f"metric-scores/{lp}/{metric_name}-{ref_name}.sys.score"
        seg_score_file.parent.mkdir(parents=True, exist_ok=True)
        log.debug(f"Writing to {seg_score_file}")
        return open(seg_score_file, "w"), open(sys_score_file, "w")

    with tqdm(zip(metas, seg_scores), desc=f"Split {scores_file.name}", total=len(metas),
              mininterval=2, disable=not Config.PBAR_ENABLED) as pbar:
        for this_id, seg_score in pbar:
            (lp, ref_name, sys_name) = this_id
            pbar.set_postfix_str(f'lp={lp}')

            if prev_id is not None and prev_id != this_id:     # new system, write previous system
                reset_sys_buffer()

            if prev_id is None or prev_id[:2] != this_id[:2]:  # new language-pair or reference: open new files
                close_files()
                seg_out, sys_out = open_files(lp, ref_name)

            seg_out.write(f"{sys_name}\t{seg_score}\n")
            sys_buffer.append(seg_score)

            prev_id = this_id

        # write last system
        if prev_id and len(sys_buffer) > 0:
            reset_sys_buffer()

    close_files()
    score_split_ok.touch()


def get_flat_file(dataset_path:Path, reference_based: bool=False, human_name=None, metric_name=None, scores_only=False, table_mode=False):
    """Flatten dataset into a single file

    :param dataset_path: dataset path (e.g., /path/to/wmt22)
    :param reference_based: _description_, defaults to False
    :return: _description_
    """

    suffix = reference_based and "wref" or "noref"
    if table_mode:
        suffix += f'.allmetrics'
    elif human_name:
        suffix += f".{human_name}"
    elif metric_name:
        suffix += f".m_{metric_name}"

    assert not (human_name and metric_name), "Only one of human_name or metric_name can be specified"
    out_path = dataset_path.parent / f"{dataset_path.name}.{suffix}.tsv"
    file_ok = out_path.with_suffix("._OK")
    if scores_only:
        assert not table_mode
        out_path = dataset_path.parent / f"{dataset_path.name}.{suffix}.score"
        file_ok = out_path.with_suffix(".score._OK")

    if not file_ok.exists():
        log.info(f"Flattening {dataset_path.name} to {out_path}")
        if table_mode:
            rows = read_flat_rows_with_all_metrics(dataset_path, skip_self_ref=True)
            #header = next(rows)     # first row as header
            #out_path.with_name(out_path.name + '.header').write_text('\t'.join(header) + '\n')

        elif human_name:
            rows = read_flat_rows_with_human(dataset_path, reference_based=reference_based, human_name=human_name)
        elif metric_name:
            rows = read_flat_rows_with_metric(dataset_path, metric_name=metric_name, reference_based=reference_based)
        else:
            rows = read_flat_rows(dataset_path, reference_based=reference_based)

        if scores_only and (human_name or metric_name):
            rows = ([x[-1]] for x in rows)
        i = 0
        with open(out_path, "w") as f:
            for row in rows:
                f.write("\t".join(row) + "\n")
                i += 1
        if i > 0:
            file_ok.touch()
    return out_path


def score_dataset(data_file: Path, out_file: Path, model_path: Path, reference_based: bool=False, toolkit="marian"):
    flag_file = out_file.with_suffix("._OK")
    if toolkit == "unbabel":
        from .unbabel import unbabel_score
        score_function = unbabel_score
    elif toolkit == "marian":
        from .marian import marian_score
        score_function = marian_score
    else:
        raise ValueError(f"Unknown toolkit: {toolkit}")

    if not out_file.exists() or not flag_file.exists():
        rows = list(read_tsv(data_file))
        #(lp, sys_name, ref_name, _src, _ref, _hyp)
        if not all(len(x) == 6 for x in rows):
            for i, r in enumerate(rows):
                if len(r) != 6:
                    log.error('ERROR::', i+1, r)
            raise ValueError(f"File {data_file} is not flattened correctly")
        srcs =  [x[3] for x in rows]
        hyps =  [x[5] for x in rows]
        if reference_based:
            refs = [x[4] for x in rows]
            seg_scores = score_function(model_path, srcs, hyps, refs=refs)
        else:
            seg_scores = score_function(model_path, srcs, hyps)
        i = 0
        with open(out_file, "w") as f:
            for score in tqdm(seg_scores, desc="Scoring", total=len(rows), mininterval=2):
                if isinstance(score, tuple):
                    score = score[0]
                f.write(f"{score}\n")
                i += 1
        assert i == len(rows), f"Number of scores does not match number of rows: {i} != {len(rows)}. See\n {data_file}\n {out_file}"
        flag_file.touch()
    else:
        log.info(f"Skip scoring {data_file.name} -> {out_file.name}")
    return out_file


def score_all(data_folder, output_folder: str, model_path: Path,
              metric_name:str, eval_dataset=None, reference_based=False,
              toolkit:str="marian"):

    data_folder = Path(data_folder)
    output_folder = Path(output_folder)
    dataset_paths = get_dataset_paths(data_folder=data_folder, eval_dataset=eval_dataset)

    for dataset_path in dataset_paths:
        # -> flatten -> score -> split
        data_file = get_flat_file(dataset_path, reference_based=reference_based)
        scores_file = output_folder / f"{data_file.name}.{metric_name}.seg.score"
        score_dataset(data_file=data_file, out_file=scores_file, model_path=model_path, toolkit=toolkit)
        flat_to_splits(data_file, scores_file, output_folder / dataset_path.name, metric_name)


def get_cached_model(model_path):
    cache_dir = Path("~/.cache/marian-models").expanduser()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached_path = cache_dir / Path(model_path).name
    flag =  cached_path / '_OK'

    if not flag.exists():
        log.info(f"Cache {model_path} -> {cached_path}")
        shutil.copytree(model_path, cached_path)
        flag.touch()
    return cached_path


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument('-m', '--model', type=str, required=True, help=f'Model path.')
    parser.add_argument('-n', '--name', type=str, required=False, help=f'Name for the metric. Default is derived from model path (i.e., dirname).')
    parser.add_argument('-c', '--cache', action='store_true', help='Cache model to local disk.')
    parser.add_argument('-b', '--base-dir', help='mt-metrics-eval dir', type=Path, default=Path(Config.METRICS_BASE_DIR))
    parser.add_argument('-u', '--user-dir', help='Directory for your own metrics', type=Path, default=Path(Config.METRICS_USER_DIR))
    args = parser.parse_args()

    # there is hardwired mean in marian_score
    cache = args.cache
    model_path = args.model
    metric_name = args.name or Path(args.model).name

    if cache:
        model_path = get_cached_model(model_path)
    score_all(data_folder=args.base_dir, eval_dataset="wmt22", model_path=model_path,
              metric_name=metric_name, output_folder=args.user_dir, reference_based=False)


if __name__ == "__main__":
    main()
