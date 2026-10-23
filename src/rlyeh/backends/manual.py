"""手动后端：自己准备图片或曲子。工具不生成，只告诉你该把文件放到哪里，放进来以后照常检查、审核。"""
from . import BackendInfo


class ManualImage:
    info = BackendInfo(id='manual', kind='image')
    edits = False                # 不会改图：差分要么直接放成品，要么把原图放进 art/_raw 再 replay art compose
    writes = False               # 等人放文件

    def __init__(self, cfg, project):
        pass


class ManualMusic:
    info = BackendInfo(id='manual', kind='music')
    generates = False            # 把曲子放进 audio/bgm/takes/<曲目ID>_<随便什么>.flac，replay music gen 会收进来
    can_plan = False

    def __init__(self, cfg, project):
        pass
