# data/ —— 外部数据放置目录 / External data directory

本目录**不存放数据文件**，只说明数据应该放在哪里、从哪里获取。

This directory holds **no data files**. It only documents where the data should
live and where to obtain it.

## 中文

数据集体积约 3.9 GB，超过 GitHub 的仓库建议上限，因此不随仓库分发。请按以下步骤自行下载后放到本目录：

1. 打开 <http://moocdata.cn/data/MOOCCube>，或 <https://github.com/thukg/MOOCCube>；
2. 下载 MOOCCube 主仓库压缩包并解压；
3. 把解压得到的 `MOOCCube/` 整个目录放到 `data/` 下，最终路径应为：

```
<仓库根>/
└── data/
    └── MOOCCube/
        ├── entities/                  # concept / course / video / user / paper ...
        ├── relations/                 # concept-concept、course-concept、user-video ...
        ├── additional_information/    # prerequisite_prediction.json ...
        └── MOOCQA/                    # 问答标注
```

4. 如需改到其他位置，设置环境变量 `MOOCCUBE_DIR` 指向该目录即可，不必改代码。

## English

The dataset is roughly 3.9 GB, which exceeds GitHub's recommended repository
size, so it is not distributed here. Download it yourself and place it here:

1. Go to <http://moocdata.cn/data/MOOCCube> or <https://github.com/thukg/MOOCCube>.
2. Download and extract the main MOOCCube archive.
3. Put the extracted `MOOCCube/` folder under `data/`, so the tree matches the
   block above.
4. To keep it elsewhere, set the environment variable `MOOCCUBE_DIR` instead of
   editing the source code.

## 许可 / License

MOOCCube 由清华大学知识工程实验室（THU-KEG）以 **CC0-1.0** 许可发布，可自由使用与再分发。

MOOCCube is released by THU-KEG under **CC0-1.0** and may be freely reused and
redistributed.

引用 / Cite:

> Yu, Jifan, et al. "MOOCCube: A Large-Scale Data Repository for NLP
> Applications in MOOCs." *Proceedings of the 58th Annual Meeting of the
> Association for Computational Linguistics*, 2020, pp. 2357–2366.

## 模型权重 / Model weights

`models/` 目录同样不在仓库中。请运行 `scripts/download_mt5.py` 下载基座模型
`google/mt5-small`，再用 `1_prototype/2.初步微调模型.py` 训练自己的策略模型。

The `models/` directory is not included either. Run
`scripts/download_mt5.py` to fetch `google/mt5-small`, then fine-tune your own
policy model with `1_prototype/2.初步微调模型.py`.
