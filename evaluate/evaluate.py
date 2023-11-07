#!/usr/bin/env python3

import pandas as pd
import scipy.stats
from pathlib import Path
from mt_metrics_eval import data

from . import log, Config


all_scenarios = {
    # comparable with Table 11
    "wmt22.mqm_tab11": {
        "testset": "wmt22",
        "focus_lps": ['en-de', 'en-ru', 'zh-en'],
        "gold_name": "mqm",
        "use_humans": False
    },
    #"wmt22.dasqm_tab11": {"testset": "wmt22",
    #                      "focus_lps": ['en-de', 'en-ru', 'zh-en'],
    #                      "gold_name": "wmt-appraise",
    #                      "use_humans": False},
    # comparable with Table 8
    "wmt22.da_sqm_tab8": {
        "testset": "wmt22",
        "focus_lps": ["en-de", "zh-en", "en-ru", 'cs-uk', 'en-hr', 'en-ja', 'en-liv', 'en-uk', 'en-zh', 'sah-ru', 'uk-cs', 'en-cs'],
        "gold_name": "wmt-appraise",
        "use_humans": True
    },
    "wmt23.mqm(de;he;zh)": {
        "testset": "wmt23",
        "focus_lps": ['en-de', 'he-en', 'zh-en'],
        "gold_name": "mqm",
        "use_humans": False
    },
    "wmt23.dasqm(de;zh)": {
        "testset": "wmt23",
        "focus_lps": ['en-de', 'zh-en'],
        "gold_name": "da-sqm",
        "use_humans": True
    },
    "wmt23.dasqm(all)": {
        "testset": "wmt23",
        "focus_lps": ["cs-uk", "de-en", "en-cs", "en-de", "en-ja", "en-zh", "ja-en", "zh-en"],
        "gold_name": "da-sqm",
        "use_humans": True
    }
}
all_scenarios = {k:v for k,v in all_scenarios.items() if v['testset'] == 'wmt23'}  # only wmt23 for now


def reformat(results):
    """Reformat CompareMetrics() results to match mtme's format."""
    metrics, sig_matrix = results
    res = {}
    for i, (m, (corr, rank)) in enumerate(metrics.items()):
        sigs = ['1' if p < 0.05 else '0' for p in sig_matrix[i]]
        sigs = ['x'] * (i + 1) + sigs[i + 1:]
        res[m] = (rank, corr, ' '.join(sigs))
    return res

def eval_metrics(eval_sets, langs, levels, primary_only, k, gold_name='std',
                 include_domains=True, seg_level_no_avg=False,
                 include_human_with_acc=False, do_reformat=True, testset_name="wmt22", quiet=False):
    """Evaluate all metrics for eval sets, across multiple task settings.

    Args:
      eval_sets: Map from lang-pair to eval_set objects.
      langs: List of language pairs (eg 'en-de') for which to compute results.
      levels: List of levels for which to compute results, allowed elements are
        'sys' and 'seg'.
      primary_only: Include only primary metrics.
      k: Number of boostrap draws. If 0, no significance tests for metric-score
        differences are run, and execution is much faster.
      gold_name: Name of gold scores to use, standard scores if 'std'.
      include_domains: Generate domain-specific results in addition to global
        results.
      seg_level_no_avg: If True, use only the average_by=None setting for segment-
        level correlations
      include_human_with_acc: If True, include human outputs in accuracy tasks.
      do_reformat: If True, reformat results to match mtme's format.

    Returns:
      Map from task names to metric -> (rank, corr, sig_string) stats.
    """
    results = {}

    # First task is global accuracy, iff more than one language is given.
    if len(langs) > 0:
        evs_list = [eval_sets[lp] for lp in langs]
        main_refs = [{evs.std_ref} for evs in evs_list]
        close_refs = [set() for evs in evs_list]
        if gold_name == 'std':
            gold = evs_list[0].StdHumanScoreName('sys')
        else:
            gold = gold_name
        humans = [True, False] if include_human_with_acc else [False]
        for human in humans:
            taskname = data.MakeTaskName(
                testset_name, langs, None, 'sys', human, 'none', 'accuracy', k, gold,
                main_refs, close_refs, False, primary_only)
            if not quiet:
                log.info(taskname)
            result = data.CompareMetricsWithGlobalAccuracy(
                evs_list, main_refs, close_refs, include_human=human,
                include_outliers=False, gold_name=gold,
                primary_metrics=primary_only,
                domain=None, k=k, pval=0.05)
            metrics, sig_matrix = result[:2]   
            if do_reformat:
                results[taskname] = reformat((metrics, sig_matrix))
            else:
                results[taskname] = {name: (rank, corr) for name, (corr, rank) in metrics.items()}

    # Remaining tasks are specific to language, domain, etc.
    for lp in langs:
        evs = eval_sets[lp]
        main_refs = {evs.std_ref}
        close_refs = set()
        for domain in [None] + (list(evs.domain_names) if include_domains else []):
            for level in levels:
                gold = evs.StdHumanScoreName(level) if gold_name == 'std' else gold_name
                for avg in 'none', 'sys', 'item':
                    if (level == 'sys' or seg_level_no_avg) and avg != 'none': continue
                    for human in True, False:
                        if human == True and len(evs.ref_names) == 1: continue  # Single ref
                        for corr in 'pearson', 'kendall':
                            corr_fcn = {'pearson': scipy.stats.pearsonr,
                                        'kendall': scipy.stats.kendalltau}[corr]
                            taskname = data.MakeTaskName(
                                testset_name, lp, domain, level, human, avg, corr, k, gold,
                                main_refs, close_refs, False, primary=primary_only)
                            if not quiet:
                                log.info(taskname)
                            corrs = data.GetCorrelations(
                                evs=evs, level=level, main_refs={evs.std_ref},
                                close_refs=close_refs, include_human=human,
                                include_outliers=False, gold_name=gold_name,
                                primary_metrics=primary_only, domain=domain)
                            result = data.CompareMetrics(
                                corrs, corr_fcn, average_by=avg, k=k, pval=0.05)
                            # Make compatible with accuracy results.
                            metrics, sig_matrix  = result[:2]
                            metrics = {evs.DisplayName(m): v for m, v in metrics.items()}
                            if do_reformat:
                                results[taskname] = reformat((metrics, sig_matrix))
                            else:
                                results[taskname] = {name: (rank, corr) for name, (corr, rank) in metrics.items()}
    return results

def eval_scenario(paths=Config.DEF_PATHS, quiet=True, scenairo_name='wmt22.da_sqm_tab8', do_reformat=False):

    scenario = all_scenarios[scenairo_name]
    eval_sets = {}
    for lp in scenario['focus_lps']:
        eval_sets[lp] = data.EvalSet(scenario['testset'], lp, True, path=paths)

    appraise_results = eval_metrics(
        eval_sets, scenario['focus_lps'], ['sys'], primary_only=False, k=0,
        gold_name = scenario['gold_name'], include_domains=False, seg_level_no_avg=True,
        include_human_with_acc=scenario['use_humans'],
        do_reformat=do_reformat, testset_name=scenario['testset'],
        quiet=quiet)
    results = appraise_results[list(appraise_results.keys())[0]]
    return results

def main(paths=Config.DEF_PATHS, out_file=None, testset_name=None):
    all_df = {}
    avail_schenarois = list(all_scenarios.keys())
    if testset_name is not None:
        avail_schenarois = [s for s in avail_schenarois if all_scenarios[s]['testset'] == testset_name]
    for scenario_name in avail_schenarois:
        results = eval_scenario(paths=paths, quiet=False, scenairo_name=scenario_name, do_reformat=True)
        log.info(f"Accuracy for scenario {scenario_name}")
        for key in results.keys():
            log.info(f"{key}\t{results[key][1]:.3f}")

        df = pd.DataFrame(results)
        df = df.transpose().drop([0,2], axis=1)
        all_df[scenario_name] = df[1]

    df = pd.DataFrame(all_df)
    if out_file is not None:
        print(df)
        df.to_csv(out_file)
        df.to_excel(out_file.replace(".csv", ".xlsx"))

if __name__ == '__main__':
    main(out_file="results.csv")
    
