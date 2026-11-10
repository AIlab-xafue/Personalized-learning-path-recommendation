# 上传到 GitHub 操作指南 / Upload Guide

从零开始，把这个仓库发布到 GitHub。每一步都给出可直接复制的命令和预期结果。

A from-scratch walkthrough to publish this repository on GitHub, with copy-paste commands and expected output for every step.

> **适用环境**：Windows 10/11 + Git for Windows（已确认你的机器装有 Git 2.55.0）
> **仓库本地路径**：`D:/workbuddy工作空间/github_release/moocube-lpr`
> **目标**：一个公开仓库，含代码、文档、实验结果，不含数据集与模型权重

---

## 0. 你将得到什么

完成后你的仓库长这样：

```
https://github.com/<你的用户名>/moocube-lpr
├── README.md            首页会自动渲染，中文
├── README_EN.md         英文版
├── LICENSE              MIT（代码）+ CC0（数据）
├── CITATION.cff         引用元数据
├── requirements.txt
├── docs/
│   ├── FILE_INDEX.md    119 个文件逐个说明（中英对照）
│   ├── DATA.md          数据获取
│   ├── UPLOAD_GUIDE.md  本文件
│   └── check_file_index.py  文件说明自检
├── 1_prototype/         阶段一代码 + 13 MB CSV
├── 2_generation/        阶段二代码 + 结果 + 9 MB 缓存
├── 3_dual_state/        阶段三代码 + 结果
├── platform/            演示平台（克隆即可跑）
├── scripts/             模型下载脚本
└── data/                先修表 55 KB + 落位说明
```

总体积约 **36 MB**，119 个文件，全部在 GitHub 限制之内。

---

## 1. 准备工作

### 1.1 注册 GitHub 账号

已有账号可跳过。

1. 打开 <https://github.com/signup>；
2. 填邮箱 → 设密码 → 起用户名（**这个用户名会出现在仓库地址里，且之后很难改**，建议用拼音或英文名）；
3. 收邮件验证。

### 1.2 确认 Git 可用

在 Git Bash 里执行：

```bash
git --version
```

预期输出类似 `git version 2.55.0.windows.3`。你的机器上已经装好了。

### 1.3 确认仓库文件就绪

```bash
cd "D:/workbuddy工作空间/github_release/moocube-lpr"
ls
```

应当看到 `README.md`、`README_EN.md`、`LICENSE`、`docs`、`1_prototype` 等。若还没有，说明发布目录没建好，先回来重新生成。

---

## 2. 第一步：在 GitHub 上创建空仓库

1. 登录 GitHub，点右上角 **`+`** → **New repository**；
2. 填写：

| 字段 | 填什么 | 说明 |
|---|---|---|
| **Repository name** | `moocube-lpr` | 建议全小写、用连字符 |
| **Description** | `Knowledge-graph-constrained personalized learning path recommendation` | 一句话，会显示在仓库标题下 |
| **Public / Private** | 选 **Public** | 老师要能访问，必须公开 |
| **Add a README file** | **不要勾** | 本地已有 README，勾了会冲突 |
| **Add .gitignore** | **None** | 本地已备好 |
| **Choose a license** | **None** | 本地已备好 |

3. 点 **Create repository**。

创建完成后页面会显示一串命令。**先不要照着做**——那个页面默认假设你本地是空的，而我们的文件已经准备好了，直接照做会出问题。

### 2.4 不装 Git 的备选路线：纯网页上传

第 3–6 章讲的都是命令行推送。如果你手上只有浏览器（例如临时借用老师的电脑），
也可以完全不装 Git，用 GitHub 网页把 119 个文件拖上去。

**代价**：丢掉本地那 4 次有意义的提交历史（网页上传只产生 1–2 个 commit），
且提交记录的署名是当前登录账号（老师的）。代码内容与命令行推送完全一致。

**可行性已核对**：119 个文件 / 35.43 MB，最大单文件 `1_prototype/database/rel_user_video.csv`
为 9.76 MB，低于网页上传单文件 25 MiB 上限。

> ⚠️ 建仓时 **Owner 必须选组织 `Allab-xafue`**，不要选成个人账号，否则仓库挂在自己名下，老师进组织看不到。

#### 步骤 1：建空仓库

同第 2 章的表格，注意三点：Owner 选 `Allab-xafue`；README / .gitignore / license **三个都留空**；
点 **Create repository**。

#### 步骤 2：进上传页面

建完仓库会跳到只有 "Quick setup" 的空白页，点页面中间那行 **`uploading an existing file`**。
也可以直接访问：

```
https://github.com/Allab-xafue/moocube-lpr/upload/main
```

#### 步骤 3：分批拖拽（关键）

GitHub 网页一次最多接受 **100 个文件**，我们有 119 个，必须分批。
每批都要**拖整个文件夹**，不要进去全选文件——只有拖文件夹才能保留 `1_prototype/database/` 这种层级。

| 批次 | 拖什么 | 文件数 | 建议 commit message |
|---|---|---|---|
| 1 | `1_prototype` 文件夹 | 24 | `add prototype code and dataset` |
| 2 | `2_generation` 文件夹 | 28 | `add generation experiments` |
| 3 | `3_dual_state` 文件夹 | 40 | `add dual-state experiments` |
| 4 | `platform` 文件夹 | 13 | `add demo platform` |
| 5 | `docs`、`data`、`scripts` 三个文件夹 | 7 | `add docs and configs` |
| 6 | 根目录 7 个文件 | 7 | `add root configs` |

第 6 批的 7 个文件：`.gitattributes`、`.gitignore`、`CITATION.cff`、`LICENSE`、
`README.md`、`README_EN.md`、`requirements.txt`。

> 看不到 `.gitignore` / `.gitattributes`？资源管理器若开了"隐藏已知文件类型的扩展名"，
> 它们会显示成 `gitignore`，这类文件最容易漏。漏了不必重传，在仓库页面用
> **Add file → Create new file**，文件名直接输 `.gitignore`，把本地内容粘进去即可。

每拖完一批，页面下方会列出待提交文件，**先确认左侧路径带 `/`**
（例如 `1_prototype/database/rel_user_video.csv`），再点绿色 **Commit changes**。

#### 步骤 4：核对传完没有

打开仓库首页，应当看到 7 个目录（`1_prototype`、`2_generation`、`3_dual_state`、
`docs`、`data`、`platform`、`scripts`）加 7 个根文件，共 14 项；
点开 `1_prototype/database` 能看到 `rel_user_video.csv`（9.76 MB）等数据文件，
点 `LICENSE` 能看到 MIT。

#### 网页路线的三个坑

1. **空目录不会被上传**——Git 本身不跟踪空目录，不影响运行；
2. **断网或卡住**——刷新页面看已提交了几批，GitHub 会保留，接着传剩下的；
3. **拖完发现文件全平铺在根目录**——说明你拖的是文件夹**里面的文件**而不是文件夹本身，删掉重拖。

### 2.5 不敲命令的备选：GitHub Desktop 图形化推送

比网页上传省事得多，而且能**完整保留本地全部提交历史**。适合"不想用命令行、但想留下开发痕迹"的场景。

#### 步骤 1：添加本地仓库

1. 打开 GitHub Desktop，菜单 **File → Add local repository...**（快捷键 `Ctrl+O`）；
2. **Local path** 点 **Choose...**，定位到 `D:\workbuddy工作空间\github_release\moocube-lpr`；
3. 点 **Add repository**。

若提示 `This directory does not appear to be a Git repository`，说明路径选错了一层（选到了父目录或子目录），
退回上一层重新选。

#### 步骤 2：确认识别正确

添加后左侧 **History** 应显示完整提交链（最早一条是 `864f42f` Initial commit），
顶部 Current branch 显示 **main**、Current repository 显示 **moocube-lpr**。三者都对才继续。

#### 步骤 3：发布（最容易出错的一步）

点顶部中间的 **Publish repository**，弹窗里填：

| 字段 | 填什么 |
|---|---|
| **Name** | `moocube-lpr` |
| **Description** | `Knowledge-graph-constrained personalized learning path recommendation` |
| **Keep this code private** | **必须取消勾选** ← 默认是勾上的，忘了就变私有，老师看不到 |
| **Owner** | 下拉选组织 **`Allab-xafue`** |

然后点 **Publish repository**。

#### 步骤 4：等推送完成

右下角有进度条，35.43 MB / 119 文件。按 500 KB/s 估算约 1–2 分钟，实际取决于网速。
完成后顶部按钮从 `Publish repository` 变成 **`Fetch origin`**，即推送结束。

#### 步骤 5：核对

浏览器打开 `https://github.com/Allab-xafue/moocube-lpr`：

- 标题下应有 **Public** 标签（显示 Private 说明步骤 3 漏了取消勾选）；
- 点 **Commits** 能看到完整提交记录，最早一条是 `Initial commit`，作者为 `SVRchen`；
- 文件列表为 7 个目录 + 7 个根文件。

#### 常见问题

| 现象 | 原因与处理 |
|---|---|
| Owner 下拉里没有 `Allab-xafue` | 组织未授权此客户端。浏览器打开 `https://github.com/organizations/Allab-xafue/settings/oauth_application_policy`，在 GitHub Desktop 那一行点 **Grant**（需组织 Owner 权限） |
| 报 `repository already exists` | 之前在网页建过同名仓库。要么网页删掉再 Publish，要么走 Repository → Repository settings → Remote 填 `https://github.com/Allab-xafue/moocube-lpr.git` 后点 **Push origin** |
| 报 `Authentication failed` | 登录过期：**File → Options → Accounts** 重新 Sign in |
| 推完发现是 Private | 网页 → **Settings** → 拉到最下 **Danger Zone** → **Change visibility** → Public |
| 提交显示灰色头像、点不开 | 提交邮箱 `1434914103@qq.com` 未在该 GitHub 账号绑定。不影响文件内容，作者名与邮箱仍完整保留在提交里 |

---

## 3. 第二步：推送前检查（这步别省）

### 3.1 确认没有超大文件

GitHub 对超过 100 MiB 的文件会**直接拒绝**整个 push，而且一旦进了提交历史，清理起来很麻烦。先查：

```bash
cd "D:/workbuddy工作空间/github_release/moocube-lpr"
find . -type f -not -path "./.git/*" -size +40M -printf "%s\t%p\n" | sort -rn
```

**预期：没有任何输出。** 如果有输出，说明有大文件混进来了，检查它是否该被 `.gitignore` 排除。

再确认总体积：

```bash
du -sh .
```

预期 **40 MB 以内**。

### 3.2 确认没有密码泄露

```bash
grep -rn "NEO4J_PASSWORD\s*=" --include="*.py" . | grep -v "os.environ"

# 再把你曾经用过的口令本身搜一遍（把尖括号换成你的旧密码）
grep -rn "<你的旧密码>" .
```

**预期：两条命令都没有输出。** 第一条如果出现结果，说明还有硬编码的数据库口令，必须先改成环境变量再提交。

> 这一步很重要。Git 的历史是永久的，密码一旦 push 上去，即使后来删掉文件，历史记录里依然能翻出来，只能靠重写历史或删库重建。

### 3.3 确认本地仓库状态

本地仓库**已经初始化并完成首次提交**（共两次提交：初始提交 + 一次修复提交），所以不需要再执行 `git init`。确认一下：

```bash
git log --oneline
git status --short
```

**预期**：`git log` 输出两行提交记录；`git status` **没有任何输出**（工作区干净）。

再看一眼被跟踪的文件清单，确认没有混入不该进仓库的东西：

```bash
git ls-files | head -30
git ls-files | wc -l
```

检查列表里**不该出现**：`.venv/`、`__pycache__/`、`models/` 以及 `data/MOOCCube/` 下除 `relations/prerequisite-dependency.json` 之外的任何文件。如果出现了，说明 `.gitignore` 没生效，先停下排查。

预期 **119 个文件**，其中 116 个是代码、文档与结果，另外 3 个是 `m1_multiseed` 的两个产物和随仓库附带的先修关系表。

---

## 4. 第三步：配置提交身份

Git 需要一个名字和邮箱来标记"是谁提交的"。你的机器上已配置过（`SVRchen` / `1434914103@qq.com`），确认一下：

```bash
git config --global user.name
git config --global user.email
```

如果没有输出，执行：

```bash
git config --global user.name "你的名字"
git config --global user.email "你的GitHub注册邮箱"
```

> 建议邮箱与 GitHub 账号一致，这样提交记录会自动关联到你的头像和主页。

顺手关掉中文文件名的转义，否则 `git status` 里中文名会显示成 `\346\225\260...` 这种乱码：

```bash
git config --global core.quotepath false
```

---

## 5. 第四步：配置认证

GitHub 从 2021 年 8 月起**不再接受账号密码**做 Git 认证，必须用下列三种方式之一。

### 方案 A：用 Git Credential Manager 弹窗（最省事，推荐）

Git for Windows 自带凭据管理器。你什么都不用配，直接跳到第 6 步执行 `git push`，会弹出一个窗口让你登录 GitHub，登录一次以后永久记住。

### 方案 B：Personal Access Token（PAT）

如果弹窗没出现或登录失败：

1. GitHub 右上角头像 → **Settings**；
2. 左侧拉到底 → **Developer settings**；
3. **Personal access tokens** → **Tokens (classic)** → **Generate new token (classic)**；
4. Note 填 `moocube-lpr push`，Expiration 选 90 天；
5. 勾选 **`repo`** 这一整个大项（这是推送代码的最小权限）；
6. 点 **Generate token**，**立刻复制**那串 `ghp_xxxx`（离开页面就再也看不到）。

推送时：

- 用户名：你的 GitHub 用户名
- 密码：**粘贴刚才那个 token**（不是账号密码）

想让 Git 记住，先执行：

```bash
git config --global credential.helper manager
```

### 方案 C：SSH 密钥（一次配置，长期免密）

```bash
# 1. 生成密钥（邮箱换成你的）
ssh-keygen -t ed25519 -C "1434914103@qq.com"
# 连按三次回车，用默认路径、不设密码短语

# 2. 复制公钥内容
cat ~/.ssh/id_ed25519.pub
```

3. 打开 GitHub → **Settings** → **SSH and GPG keys** → **New SSH key**；
4. Title 随便填，Key 里粘贴刚才复制的内容，保存；
5. 测试：

```bash
ssh -T git@github.com
```

看到 `Hi <用户名>! You've successfully authenticated...` 就成功了（提示 `does not provide shell access` 是正常的）。

用 SSH 的话，第 6 步的远程地址要换成 `git@github.com:<用户名>/moocube-lpr.git`。

---

## 6. 第五步：添加远程地址并推送

提交已经在本地做好了，这一步只需要接上远程仓库再推上去。

```bash
cd "D:/workbuddy工作空间/github_release/moocube-lpr"

# 1. 添加远程仓库（用户名换成你的）
git remote add origin https://github.com/<你的用户名>/moocube-lpr.git

# 2. 确认远程地址没写错
git remote -v

# 3. 推送（-u 表示把本地 main 与远程 main 绑定，以后直接 git push 即可）
git push -u origin main
```

> 如果你的默认分支名不是 `main`（用 `git branch --show-current` 可查），把上面命令里的 `main` 换成实际分支名。

**预期输出**：

```
Enumerating objects: 130, done.
Counting objects: 100% (130/130), done.
...
To https://github.com/<用户名>/moocube-lpr.git
 * [new branch]      main -> main
branch 'main' set up to track 'origin/main'.
```

**推送体积约 36 MB**，视网速需要几十秒到几分钟。如果卡住超过 5 分钟且无进度，按 `Ctrl+C` 中断，改用第 5 步方案 B 的 token 重试（常见原因是认证方式没配对）。

推送完成后刷新 GitHub 页面，应该能看到 README 渲染出来的中文首页。

---

## 7. 第六步：把仓库"门面"补齐

代码上去了，但仓库还缺几样让老师一眼看懂的东西。

### 7.1 确认 README 正常渲染

打开仓库首页，检查：

- 标题、徽章、目录是否正常显示；
- 中文是否乱码（GitHub 默认 UTF-8，一般不会）；
- 点击 `docs/FILE_INDEX.md`、`docs/DATA.md` 等链接能否跳转。

若某个相对链接 404，检查文件名大小写是否与链接一致。

### 7.2 填 About 与 Topics

仓库首页右侧 **About** 旁边的齿轮：

- **Description**：`Knowledge-graph-constrained personalized learning path recommendation: generation, dual-state execution, rolling replanning`
- **Website**：暂时留空（有演示页面再填）
- **Topics** 建议填（回车分隔）：

```
knowledge-graph  learning-path-recommendation  mooc  constrained-decoding
mt5  personalized-learning  educational-data-mining  python
```

Topics 会影响别人能否搜到你的仓库。

### 7.3 检查文件语言统计

首页右侧会显示语言占比。如果显示大量 `JavaScript`（因为 `echarts.min.js` 约 1 MB），可以用 `.gitattributes` 把它标为文档类，避免统计失真：

```bash
echo "platform/assets/echarts.min.js linguist-vendored" >> .gitattributes
git add .gitattributes
git commit -m "chore: mark vendored ECharts bundle"
git push
```

### 7.4 发一个 Release（可选，但推荐）

老师的常见疑问是"数据在哪"。用 Release 说明一次：

1. 仓库页右侧 **Releases** → **Create a new release**；
2. Tag 填 `v1.0`，Target 选 `main`；
3. Title：`v1.0 — 学位论文配套代码与中期成果`；
4. 描述里写清：数据集请按 `docs/DATA.md` 下载，模型权需按 `1_prototype/` 自行训练；
5. 点 **Publish release**。

若你有**小样本数据**（单文件 < 25 MiB），可以在这里作为附件上传，比塞进 Git 仓库合适得多。

---

## 8. 第七步：以后怎么更新

改完代码后，三步走：

```bash
cd "D:/workbuddy工作空间/github_release/moocube-lpr"

git status                      # 看改了哪些文件
git add -A                      # 全部加入暂存区（也可只加单个文件）
git commit -m "描述这次改了什么"
git push
```

**提交信息怎么写**（老师会看）：

| 好的写法 | 差的写法 |
|---|---|
| `feat: 新增预算收紧实验 D5` | `update` |
| `fix: 修正重规划触发条件的边界判断` | `修改` |
| `docs: 补充文件说明中的输入输出` | `123` |
| `refactor: 把硬编码路径改为环境变量` | `xx` |

如果改的是第 2、3 阶段的脚本并重新跑了实验，记得把 `*_outputs/` 下更新的结果一起提交，否则代码与数据会对不上。

---

## 9. 常见错误与解决

| 报错 | 原因 | 解决 |
|---|---|---|
| `remote origin already exists` | 已经加过远程地址 | `git remote set-url origin <新地址>` |
| `failed to push some refs` / `non-fast-forward` | 远程有你本地没有的提交（多半是建仓时勾了 README） | `git pull --rebase origin main` 再 push |
| `Authentication failed` | 用了账号密码 | 改用 PAT 或 SSH，见第 5 步 |
| `file is 123.45 MB; this exceeds GitHub's file size limit of 100.00 MB` | 大文件混进提交 | 见下方"文件已在提交历史里" |
| `RPC failed; curl 56` | 网络中断 | `git config --global http.postBuffer 524288000` 后重试 |
| `LF will be replaced by CRLF` | Windows 换行符提示 | 无害警告，可忽略 |
| 中文文件名显示成 `\346\225\260` | 未关转义 | `git config --global core.quotepath false` |

### 文件已经在提交历史里了，怎么办

如果大文件已经 commit 但**还没 push**：

```bash
git reset --soft HEAD~1        # 撤销提交，保留文件
# 把大文件加入 .gitignore
git rm --cached 大文件路径
git commit -m "重新提交，排除大文件"
```

如果**已经 push 上去**，需要重写历史（较复杂，建议用 `git filter-repo`），或干脆删掉远程仓库重建——对这个项目而言，**重建更快也更干净**：

1. GitHub 仓库 → Settings → 拉到底 → **Delete this repository**；
2. 回到第 2 步重新创建，这次不要勾 README；
3. 本地执行 `git remote set-url origin <新地址>` 后重新 push。

---

## 10. 可选：加一个引用文件

学术仓库加 `CITATION.cff` 后，GitHub 首页右侧会出现 **"Cite this repository"** 按钮，评审看了会觉得规范。本仓库已附带该文件，如无则手动创建（内容见仓库根目录）。

---

## 11. 检查清单

推送完成后逐项打勾：

- [ ] 仓库是 **Public**
- [ ] 首页 README 正常渲染，中英文链接可跳转
- [ ] `docs/FILE_INDEX.md` 能打开，表格不错行
- [ ] 文件说明没有遗漏：`python docs/check_file_index.py` 输出「全部 N 个文件均已说明」且退出码为 0
- [ ] 仓库体积 < 100 MB（首页右侧或 Settings 里可看）
- [ ] **没有** `models/`、`data/MOOCCube/`、`.venv/` 目录
- [ ] 全部 `.py` 文件里搜不到任何硬编码口令（`NEO4J_PASSWORD` 只应出现在 `os.environ.get` 里）
- [ ] About 的 Description 与 Topics 已填
- [ ] 克隆到新目录能跑通演示平台：

```bash
cd /tmp
git clone https://github.com/<你的用户名>/moocube-lpr.git test-clone
cd test-clone/platform
python server.py
```

最后一条最能说明问题：**别人克隆下来能不能跑**。建议 push 完就自己试一次。
