# Agent 操作入口

## 共用開發流程

- 主要使用 Codex Remote 與 GitHub 原生 CI/CD；一般開發不依賴 Dispatcher／Runner、派工白名單或 codex-ready。
- Agent 依工作規模決定是否建立 Issue，先定義驗收條件；需要持久追蹤的任務與依賴使用 GitHub Issues，Projects 僅顯示進度。
- 可連續開發與多次 Commit，以可獨立整合的功能單位建立 PR；不要求每次修改建立 PR。
- 自動執行必要測試與 Code Review。只有風險明確為低、驗收通過、確切 PR head 的可信 CI 成功，且 GitHub 合併保護有效時，才使用原生 auto-merge；不 bypass、不直接推送受保護分支。
- 安全、權限、重要資料、交易風控、受保護政策及實機驗收相關變更，Merge 前必須取得人工核准。風險不明或證據不足不得自動放行；既有 Frozen、產品授權、Stop／hold 與實機 Gate 保持有效。
- 只沿用有實際部署需求且已授權的 CD；保留 GitHub environment 的人工門檻。CI／Merge／部署／實機結果分別驗證，不以空測試、跳過測試或降低保護取得 PASS。
