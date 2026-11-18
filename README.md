# 启衡材料试验室交班台账

白班按固定清册采集门户的具名试片读数。夜班在门户停用后按回执复核并签发报告，班次负责人可凭报告号追溯每片读数的原始页行。门户的行序和列序可以与清册不同，源刻度也可与验收刻度不同。

在项目根目录用 Python 3.11 运行，无需安装依赖。

```sh
python3 -B -m unittest discover -s tests -t . -v
python3 -B -m demo
```

演示把 `samples/` 中的资料导入独立临时库，先拒绝缺片录制，再发布完整录制。关闭来源和数据库连接后，演示重开归档，读回 x=20、y=22，按各片上限 20 签发，沿报告追到原页行。

匿名双样演示 `python3 -B -m demo_pairs` 另开临时库，从录制门户取出 `path` 与 `independent` 两批，接纳后停用来源并关闭归档；重开后只凭两个回执领取 x/z，分别得到 2 对和 4 对。交班说明见 `PAIR_HANDOFF.md`。

## 接口

用 `archive.database.open_archive(path)` 打开 SQLite 连接。依次调用 `runs.storage.init_roster_store(db)`、`archive.database.init_archive(db)` 和 `review.storage.init_report_store(db)` 建立持久结构。可在重开后重复初始化。登记、接纳和签发自行管理事务，应在连接空闲时调用。连接由调用者关闭。

| 入口 | 成功结果 |
| --- | --- |
| `runs.registry.register(db, batch_id, version, specimens, limits, scale)` | 固定登记号 |
| `runs.registry.get_roster(db, registration_id)` | 固定清册及登记号 |
| `portal.source.RecordedPortal({batch_id: path}).fetch_recording(batch_id)` | 本地模拟门户的原件字节 |
| `intake.accept.import_named(db, registration_id, raw)` | 已发布的采集回执 |
| `archive.readings.get_capture(db, receipt)` | 已核验的登记绑定与有序读数 |
| `archive.readings.read_capture_evidence(db, receipt)` | `(capture, original_bytes)`，二者一起核验 |
| `review.issue.issue_review(db, receipt)` | 已提交的 `ReviewReport`，含 `report_id` |
| `review.issue.get_report(db, report_id)` | 指定报告号固定的签发快照 |
| `intake.accept.ingest_pairs(db, batch_id, roster, exports)` | 已发布匿名批次回执（即批次标识） |
| `archive.readings.read_pair(db, receipt, left, right)` | 该匿名回执内两片可同时成立的有序值对 |

`specimens` 是非空的有序试片号序列。`limits` 以试片号为键，恰好为每片提供一个整数上限。`scale` 接受整数分子与分母组成的二元序列，或 `Fraction`，比值必须为正。清册保留原顺序。重登同版相同内容沿用原登记号，同版改变顺序或内容会发生冲突。登记新版本后，旧版仍可引用。

录制为 UTF-8 JSON 对象，含 `batch_id`、`source_scale` 和 `pages`。源刻度是两个整数构成的数组。页号 `page_id` 在录制中唯一，`columns` 中的 `specimen_id` 和 `reading` 各出现一次，`rows` 的每行按该页列声明排列。原数据行从 1 起算。每片恰有一行。标准读值等于原整数乘源刻度再除以标准刻度，结果必须是精确整数。零和负值有效，空值和布尔值无效。

回执与原件一同发布。同登记号下提交相同原件字节会沿用已有回执。两份不同且有效的录制各自固定。按回执领取时验证原件、登记绑定和有序读数。签发按该回执对应版本的逐片上限复核，等于上限时通过。报告中保留原回执、登记号、版本、有序裁决和越限项。需要追溯时，用报告的回执读取已核验原件，在指定页的原始行号查找。

无效输入和同版冲突抛出 `ValueError` 的子类。未知登记、回执或报告抛出 `KeyError` 的子类。固定证据缺失或不一致抛出 `EvidenceMismatch`。来源停用或文件读取失败抛出 `OSError` 的子类。SQLite 错误向调用方传播，未提交的写入回滚。`import_named` 和 `issue_review` 接受可选的 `before_commit(db)` 回调，用于受控验证提交失败；回调在新写入完成后、事务提交前执行，不能结束事务。
