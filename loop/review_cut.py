"""Explicit, local-only review cuts. Never changes the production variety rule."""
import os
from pathlib import Path


def enabled():
    return os.environ.get('HWK_REVIEW_CUT') == '1'


def refuse_publish(path=None):
    if enabled() or (path and any('review' in p.lower() for p in Path(path).parts)):
        raise RuntimeError('REVIEW_CUT_LOCAL_ONLY: refusing to shelve, push or upload')


def output_path(path):
    p = Path(path).resolve()
    if enabled():
        if not any(part.startswith('review-') for part in p.parent.parts) or not p.name.endswith('-review.mp4'):
            raise RuntimeError('REVIEW_CUT_LOCAL_ONLY: use a review directory and -review.mp4')
        if p.exists() or Path(str(p) + '.footage.json').exists():
            raise FileExistsError(f'REVIEW_CUT_NO_OVERWRITE: {p}')
    return p
