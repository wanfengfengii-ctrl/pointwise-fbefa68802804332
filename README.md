# 启衡双站量具比测分析台

白班计量员根据参考件约束及样品读数单冻结甲乙站件。夜班分析员在两站关闭后凭指定实收件核定近读对数和免补测资格。次班班长按号领取原报告及出处，安排需补测的请求。

## 运行

需要 Python 3.11 和标准库。控制台物化项目时提供 `check_project.py`。完整回归和演示分别运行：

```console
python3 -B check_project.py
python3 -B demo.py
```

也可直接发现整个 unittest 套件：

```console
python3 -B -m unittest discover -s tests -t .
```

演示使用三个临时 SQLite 库，执行登记、冻结、发行、实收、闭站签发、追加勘误和中心重开。它输出手算预期、实际签报结果及下游结果。示例夹具不会进入使用者的业务库。

## 业务接口

连接由调用方创建并关闭。使用 SQLite 默认连接设置即可。写入口要求空闲连接，由入口提交或回滚自己的事务。各账本的 `initialize()` 可重复调用，保留已登记数据。

| 接口 | Python 调用与结果 |
| --- | --- |
| I1 登记 | `RevisionStore(db).register_draft(station_id, samples, constraints, corrects_revision_id=None)` 返回稿号。`Sample(name, reading)` 保存具名原读数。`ReferenceConstraint(reference_id, gain, offset, relation, bound)` 表示 `gain*a + offset*b relation bound`，关系取 `<=`、`>=` 或 `==`。勘误须指向本站冻结修订。 |
| I2 冻结 | `freeze_revision(revisions, station_id, draft_id)` 返回冻结修订号。同一稿号再次冻结复用其修订。可用 `load_draft`、`load_frozen` 查站内原记录。失败稿保留，可据其登记修正稿。 |
| I3 发行 | `IssueRegister(revisions).issue_revision(station_id, revision_id)` 返回 `StationEnvelope`。`encode_envelope` 生成来件字节。发行记录可在站端用 `load_issue(issue_id)` 领取。 |
| I4 实收 | `receive_delivery(receipts, payload, issue_id=..., station_id=..., revision_id=...)` 以随件通知的三个标识验收正文，返回 `Receipt`。使用 `ReceiptStore(db).load_receipt(receipt_id)` 复领。 |
| I5 核定 | `run_comparison(receipts, ledger, ComparisonRequest(left_receipt_id, right_receipt_id, tolerance, threshold))` 返回已提交的 `FinalizedReport`。`ledger` 为 `ReportLedger(db)`。报告带标识、原参数、可达谱、资格、有序父件和发布回执。 |
| I6 领取 | `read_report(ledger, report_id)` 返回原定稿和回执。`export_report(ledger, report_id)` 返回发布时保存的 JSON 字节。 |

站库用 `RevisionStore` 和 `IssueRegister` 初始化，中心库用 `ReceiptStore` 和 `ReportLedger` 初始化。输入非法或来件冲突引发 `ValueError`，未知标识引发 `LookupError`，实际存储失败由 SQLite 异常通知。数据库写入失败时不会返回成功回执。

## 标定、交接与计算口径

样品清单含一至三件，名称在修订内唯一，读数单位为毫米。录入和请求中的有理数接受 `int`、`Fraction` 或 Python 3.11 `Fraction` 支持的有理数字符串。布尔值和浮点数不属于数值输入。容差非负，门槛为整数。冻结要求全部参考约束同时成立，形成非空、有界的闭域，且每个可行增益 `a` 均大于零。单点和线段也可冻结。

V1 外层含 `version`、`station_id`、`revision_id`、`issue_id` 和 `body`。正文的 `samples` 给出坐标顺序，`vertices` 给出生成整组修正读值凸包的向量。每个有理数编码为最简的 `[分子, 正分母]`。原读数及参考记录留站。中心将规范件的 SHA-256 摘要与实际首件字节入账。重复送达同一规范件时复用实际首件和首执。同号异件、重复 JSON 字段和不完整正文均拒绝。

中心在每份站件内各选一个可行的整组读值，将这两个选择用于整张样品交叉表。读值绝对差小于等于容差时计一对，同值异名仍各有身份。结果是全部可达整数对数的升序列表。可能只在一个点达到某个计数，也可能跳过中间计数。只有最小可达对数达到门槛时才免补测。

工作日样例的甲乙原测各为 `0,1`。初版甲增益为 3，零点为 `t∈[0,2]`。乙增益为 5、零点为 0。零容差时，甲首件与乙首件只在 `t=0` 相等，甲末件与乙末件只在 `t=2` 相等，得到 `[0,1]`。容差为 1 时两条闭条件在 `t=1` 同时成立，得到 `[1,2]`。甲站勘误改为 `a+2b=5`、`b=t∈[0,2]`，固定件表达 `(t,5−t)`，零容差得到 `[0,2]`。两个甲件的单件范围一致，联合关系不同。

未实收及同站错件在发布前拒绝。每份报告与发布回执原子入账。勘误及重开后，旧定稿仍绑定原实收件，领取和导出使用已提交快照。
