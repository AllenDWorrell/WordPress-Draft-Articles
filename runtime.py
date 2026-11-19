"""Windows runtime and packaged-resource path helpers."""
import os
import sys
from pathlib import Path


def packaged_root():
    return Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))


def user_data_dir(app_name='TheCurrent'):
    override=os.environ.get('THE_CURRENT_DATA_DIR')
    if override:
        return Path(override).expanduser()
    if getattr(sys,'frozen',False):
        base=Path(os.environ['LOCALAPPDATA']) if os.environ.get('LOCALAPPDATA') else Path.home()/'.the-current'
        return base/app_name
    return packaged_root()/'native-data'
