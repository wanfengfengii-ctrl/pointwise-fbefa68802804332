# 容差谱交班

现有登记、冻结、发行、实收和固定容差报告见 `README.md`。区间签发使用同样的两份 V1 站件和中心实收号。在每个容差上，凡是至少有一组双站联合读值能使整表恰好计得该对数，该容差就属于该对数的集合。同值异名仍逐对计，等于容差的差值也计入。

## 调用约定

| 调用 | 输入与输出 |
| --- | --- |
| `compare.RangeComparisonRequest(left_receipt_id, right_receipt_id, lower, upper, threshold)` | 左右顺序由调用方指定，两件须来自异站。上下界沿用 V1 有理数输入，满足 `0 <= lower <= upper`，单位 mm。门槛沿用 V1 整数口径。 |
| `compare.run_range_comparison(receipts, ledger, request)` | 使用已有 `ReceiptStore` 和 `ReportLedger`，在空闲连接上签发，返回已入账的区间定稿。 |
| `report.read_range_report(ledger, report_id)` | 返回原号区间定稿，连同原发布回执和有序出处。 |
| `report.export_range_report(ledger, report_id)` | 返回签发时保存的 UTF-8 JSON 字节。 |
| `report.query_range(report, tolerance)` | 接收签发或领取所得的区间定稿和窗内有理容差。返回 `(counts, waiver)`，`counts` 为升序整数元组，`waiver` 为布尔值。仅使用传入定稿即可查询。 |

区间定稿公开 `report_id`、`lower`、`upper`、`threshold`、`spectrum`、`sources` 和 `receipt`。两个窗界是 `Fraction`。`sources` 和 `receipt` 沿用 V1 的 `ParentSource` 有序二元组及 `PublicationReceipt`，包括确切实收号、发行号、站号、修订号、摘要和实际发布回执。`spectrum` 为按对数升序的 `(count, intervals)` 元组序列，`intervals` 是按左端点升序的区间元组。区间公开 `lower`、`upper` 两个 `Fraction` 和 `lower_closed`、`upper_closed` 两个布尔值。多个区间的并集若仍是单个区间，须合并。共享同一端点但两侧均排除该点时分开。单点用相等且均纳入的端点表示。省略没有可达容差的对数。

JSON 顶层保留上述字段并加 `kind`，其值为 `tolerance-range`。窗界和区间端点沿用 V1 最简 `[分子, 正分母]` 编码。`spectrum` 是 `[count, intervals]` 条目的数组，`intervals` 是含上述四个区间字段的对象数组。`sources` 和 `receipt` 沿用 V1 的字段和含义。领取及导出所用谱和回执来自签发时存值。最小可达对数达到原门槛即免补测。

非法输入、同站错件、窗外设点和在区间领取、导出或查询中误用 V1 点报时抛 `ValueError`。合法但未知的实收号或报告号抛 `LookupError`。数据库失败按 V1 抛 SQLite 异常，本次定稿和回执均未新增，可重试。保留所有原接口、站件字节和 V1 报告字节。

## 交班样例

`range_examples.make_items()` 返回可由 `demo.accept` 从现有入口实收的原站件。生成完即关闭站库。`python3 -B range_examples.py` 通过 V1 入口核对其中的离散设点。下表给出完整区间签发的预期，每个 `对数 → 集合` 均指同一行窗口内的结果。

| 样例键 | 窗口（mm） | 精确可达容差 |
| --- | --- | --- |
| `initial` | `[0,2]` | `0 → [0,1)`，`1 → [0,2)`，`2 → [1,2]` |
| `initial` | `[1,1]` | `1 → {1}`，`2 → {1}` |
| `correction` | `[0,2]` | `0 → [0,2)`，`2 → [0,2]` |
| `duplicates` | `[0,2]` | `0 → [0,1)`，`4 → [1,2]` |
| `full_rank` | `[0,1]` | `0 → [0,1]`，`1 → [0,1]`，`2 → [1/2,1]` |
| `separated` | `[0,2]` | `0 → [0,3/2)`，`1 → [0,1) ∪ (1,2)`，`2 → [1/2,2]` |

初版甲读值是 `(t,t+3)`，乙是 `(0,5)`，`t` 在 `[0,2]`。窗内两条可能计入的差值为 `t` 和 `2−t`，在 1 mm 首次同时达标。勘误版甲为 `(t,5−t)`，两条差值均为 `t`。初版用门槛 2 签 `[0,2]`，1 mm 领到 `((1, 2), False)`，2 mm 领到 `((2,), True)`。勘误件另签后，1 mm 领到 `((0, 2), False)`，初版报告仍给出原裁决。

`full_rank` 两站的增益和零点各自是独立闭区间。两条可计读差之间至少相隔 1 mm，因此至少要给 `1/2` mm 的容差才可同时吻合。`separated` 的甲读值为 `(t,2t+4)`，乙仍为 `(0,5)`，`t` 在 `[1/2,3/2]`。两条可计绝对差是 `t` 和 `2t−1`。在 1 mm，两条一起计入或一起落在窗外。紧邻两侧都可只计一条。

先实收并签发初版，再实收勘误件并另签。可参照 `tests/test_history.py` 重开中心后禁止读取 `receipts`，核对两份报告的领件、导出、回执、左右出处及 1 mm 的不同裁决。该文件也有第二笔写入失败的 SQLite 触发器示例，可在区间发布边界核对失败无新增和撤除阻断后可再办。

## 验证与演示

`.pointwise-runtime.json` 沿用 `version` 为 `1` 和 `kind` 为 `cli`。`setup` 是准备命令的参数数组列表，标准库项目可留空。`verify` 与 `demo` 各是一条命令的参数数组。交付时让 `verify` 执行原回归与这次区间签发的业务核对，错误返回非零退出码。`demo` 使用实际签发和领取结果展示闭站签发、重开复领及设点裁决。
