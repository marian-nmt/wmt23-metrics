import os
import glob
import collections
import logging as log

from mt_metrics_eval import data


log.basicConfig(level=log.INFO)


def ReadScoreFile(filename, select=None):
    scores = collections.defaultdict(list)  # sys -> [scores]
    skips = set()
    with open(filename) as f:
        for line in f:
            sysname, score = line.split()
            if select is not None and sysname not in select:
                skips.add(sysname)
                continue  # Skip systems not in select.
            scores[sysname].append(float(score) if score != 'None' else None)
    if skips:
        log.info('%s : skipping %d systems not in select: %s',
                 filename, len(skips), skips)
    return scores


class EvalSet(data.EvalSet):
    """ Overrriding mtme.data.Evalset to skip erroneous systems"""

    def _ReadDataset(self, name, lp, read_stored_metric_scores, path, strict):
        """Read data for given name and language pair."""

        if path is None:
            path = data.LocalDir(root_only=False)
            if not os.path.exists(path):
                raise ValueError('%s not found. Run mtme --download.' % path)

        if isinstance(path, list):
            metric_scores_paths = path
            path = path[0]  # Use first path for dataset resource files.
        else:
            metric_scores_paths = [path]

        d = os.path.join(path, name)
        doc_lines = data._ReadTextFile(
            os.path.join(d, 'documents', '%s.docs' % lp))
        self._domains = data._MapPositions([d.split()[0] for d in doc_lines])
        # Canonicalized domain order, since there is no natural order.
        self._domains = {k: self._domains[k] for k in sorted(self._domains)}
        self._docs = data._MapPositions(
            [d.split()[1] for d in doc_lines], True)
        self._src = data._ReadTextFile(
            os.path.join(d, 'sources', '%s.txt' % lp))

        self._all_refs = {}
        for filename in glob.glob(os.path.join(d, 'references', '%s.*.txt' % lp)):
            refname = filename.split('.')[-2]
            if '-' in refname or refname in ['all', 'src']:
                assert False, f'Invalid reference name: {refname}'
            self._all_refs[refname] = data._ReadTextFile(filename)

        self._outlier_sys_names, self._human_sys_names = set(), set()
        self._sys_outputs = {}
        for filename in glob.glob(os.path.join(d, 'system-outputs', lp, '*.txt')):
            sysname = os.path.basename(filename)[:-len('.txt')]
            self._sys_outputs[sysname] = data._ReadTextFile(filename)
            if sysname in self._all_refs:
                self._human_sys_names.add(sysname)

        self._human_score_names = set()
        self._scores = {}
        selected_sys_names = set(
            self._sys_outputs.keys())  # ones having outputs
        for filename in glob.glob(
                os.path.join(d, 'human-scores', '%s.*.score' % lp)):
            lp, scorer, level = self.ParseHumanScoreFilename(
                os.path.basename(filename))
            self._human_score_names.add(scorer)
            if level not in self._scores:
                self._scores[level] = {}
            assert scorer not in self._scores[level], scorer
            if level == 'domain':
                self._scores[level][scorer] = data.ReadDomainScoreFile(
                    filename, self.domain_names)
            else:
                self._scores[level][scorer] = ReadScoreFile(
                    filename, select=selected_sys_names)

        self._metric_names = set()
        self._metric_basenames = set()
        if read_stored_metric_scores:
            for md in metric_scores_paths:
                md = os.path.join(md, name)
                for filename in glob.glob(
                        os.path.join(md, 'metric-scores', lp, '*.score')):
                    scorer, level = self.ParseMetricFilename(filename)
                    if level not in self._scores:
                        self._scores[level] = {}
                    assert scorer not in self._scores[level]
                    assert self.ReferencesUsed(scorer).issubset(self.ref_names)
                    self._metric_names.add(scorer)
                    self._metric_basenames.add(self.BaseMetric(scorer))
                    if level == 'domain':
                        self._scores[level][scorer] = data.ReadDomainScoreFile(
                            filename, self.domain_names)
                    else:
                        self._scores[level][scorer] = ReadScoreFile(
                            filename, select=selected_sys_names)

        # Check contents
        for txt in self.all_refs.values():
            assert len(txt) == len(self.src), f'Bad length for reference {txt}'
        for txt in self.sys_outputs.values():
            assert len(txt) == len(self.src), f'Bad length for output {txt}'
        for level in self._scores:
            for scorer_name, scores_map in self._scores[level].items():
                try:
                    self.CheckScores(scores_map, scorer_name, level,
                                     scorer_name in self.human_score_names,
                                     repair=not strict)
                except:
                    # breakpoint()
                    raise
