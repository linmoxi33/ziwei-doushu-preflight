# ziwei-doushu-preflight

离线预测 `ziwei-doushu` 的 `generateChart()` 会**静默**怎样改写你的出生信息——在错盘生成之前给出退出码。

Upstream: https://github.com/Renhuai123/ziwei-doushu

为什么现在需要它：上游排盘引擎对 `hour` 和日期会抛 `RangeError`，但对 `gender` 和 `longitude` 不抛——
传错性别会直接得到一张按女命排的完整盘，传了经度则被完全丢弃。2026-10-31 这两个缺口仍是 open issue
（[#38](https://github.com/Renhuai123/ziwei-doushu/issues/38)、[#45](https://github.com/Renhuai123/ziwei-doushu/issues/45)），
修复 PR [#49](https://github.com/Renhuai123/ziwei-doushu/pull/49)、[#50](https://github.com/Renhuai123/ziwei-doushu/pull/50) 尚未合并。

## 上游是什么、缺什么

`ziwei-doushu` 是紫微斗数排盘引擎（TypeScript，MIT），`lib/ziwei/algorithm.ts` 的 `generateChart(birthInfo)` 是公开入口，
`BirthInfo.longitude` 在 `types.ts` 中标注「用于真太阳时校正」。

缺口的源码本体只有两行：

- [`algorithm.ts#L448`](https://github.com/Renhuai123/ziwei-doushu/blob/495b79ecb3524b20b2edc026067d7d0b0f407319/lib/ziwei/algorithm.ts#L448)
  `const { year, month, day, hour, gender } = birthInfo;` —— `longitude` 没有进入函数作用域，后续无分支可读它。
- [`algorithm.ts#L461`](https://github.com/Renhuai123/ziwei-doushu/blob/495b79ecb3524b20b2edc026067d7d0b0f407319/lib/ziwei/algorithm.ts#L461)
  `const iztroGender = gender === 'male' ? '男' : '女';` —— 任何非 `'male'` 值都静默变成女命。

上游 README 自己也承认数据口径「按时辰序号直接排盘，未按出生地做真太阳时校正」
（[README.md#L148](https://github.com/Renhuai123/ziwei-doushu/blob/main/README.md#L148)），
但同文件 L309 又把「真太阳时校正」列为引擎能力——两条说法互相矛盾，调用方无从判断该信哪条。

## 这个工具做什么、不做什么

做：读取 `BirthInfo` JSON / JSONL，按上游源码的真实行为逐条预测

| 代码 | 级别 | 含义 |
| --- | --- | --- |
| `E_GENDER_COERCED` | error | `gender` 不是 `male`/`female`，引擎会排成女命（L461） |
| `E_GENDER_MISSING` | error | 缺 `gender`，同样落到女命分支 |
| `E_HOUR_RANGE` | error | `hour` 不是 0–11 的时辰序号（不是钟点），引擎抛 `RangeError` |
| `E_DATE_NOT_EXIST` | error | 2 月 30 日、非闰年 2 月 29 日等，引擎抛 `RangeError` |
| `E_DATE_TYPE` | error | 年/月/日不是整数 |
| `E_LONGITUDE_RANGE` | error | 经度不在 [-180, 180] |
| `E_LONGITUDE_CHANGES_BRANCH` | error | 经度被丢弃，但真太阳时校正足以跨时辰——盘会算在错误的时辰支上 |
| `W_LONGITUDE_IGNORED` | warning | 传了经度但引擎不读（L448） |
| `W_CITY_WITHOUT_LONGITUDE` | warning | 有出生地、无经度，无法校正 |
| `W_DST_WINDOW` | warning | 钟表时间落在中国夏令时区间（1986–1991），引擎只判定、不自动减 1 小时 |
| `W_UNKNOWN_FIELD` | warning | 字段不属于 `BirthInfo`，会被引擎丢掉（例如拼错的 `longtitude`） |

不做：不排盘、不解释命盘、不联网、不修改上游。时辰跨越判定只用上游 `share.ts` 同款经度差
`(longitude − 120) × 4` 分钟，不含均时差——这是上游应用路径的口径，不是本工具自创。

## 安装 / 用法

无第三方依赖，Python 3.8+：

```bash
python3 bin/ziwei-preflight examples/in/births.json
```

带 JSON 输出（可被 `json.load` 直接解析）：

```bash
python3 bin/ziwei-preflight --json examples/in/births.json
```

输入既可以是单个对象、对象数组，也可以是 `.jsonl`（每行一条）。样例输出见
`examples/out/report.json`（对 `examples/in/births.json` 的真实运行结果，3 条记录、3 error、1 warning、退出码 1）。

JSON 结构：`{tool, version, upstream, records, summary:{errors,warnings,clean}, findings:[{code,severity,record,field,message}]}`。

退出码：

| 码 | 含义 |
| --- | --- |
| 0 | 没有 error 级发现（warning 不影响通过） |
| 1 | 至少一条 error 级发现，盘会错 |
| 2 | 用法错误、文件不可读、JSON 解析失败 |

## 与同类项目的差异

`gh search repos "ziwei doushu"`（2026-10-31）命中的是排盘站点、skill、API 封装（最高 2514 stars 的
`DestinyLinker/MingLi-Bench` 是 LLM 评测集，不是输入校验器）；`gh search code "generateChart birthInfo"`
零命中。本工具不排盘、不封装引擎，只做「上游会静默做什么」的可执行契约，因此与上述项目无功能重叠。

## 本轮创新

把「输入校验」做成**静默强转预测**：不只说字段非法，而是按上游源码复现它会怎么兜底，并把被丢弃的经度换算成
「会不会跨时辰」的确定性结论（`午时 -> 巳时`）。已有的排盘库和 skill 都只消费排盘结果，没人对
`generateChart` 的静默行为做可断言的契约测试——这是第一个。

## 局限

- 规则锚定 commit `495b79e`（2026-10-31）。上游合并 #49/#50 后，性别与经度两条 error 会失效，需要同步更新。
- 只覆盖 `generateChart` 的直接入参，不覆盖 `astro.bySolar` 内部对农历/闰月的处理。
- 夏令时表只覆盖 1986–1991（上游 `dst-cn.ts` 中与「中国大陆夏令时」相关、且被 README 承诺的区间）。
- 跨时辰判定忽略均时差（最大约 ±16 分钟），边界附近可能少报；这是保守方向，不会误报成 error。

## 证据

- issue #38（open）：https://github.com/Renhuai123/ziwei-doushu/issues/38
- issue #45（open）：https://github.com/Renhuai123/ziwei-doushu/issues/45
- README 限制段：https://github.com/Renhuai123/ziwei-doushu/blob/main/README.md#L148

## License

MIT
