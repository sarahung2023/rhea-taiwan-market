RHEA｜台股外部情報中心 v1.0｜2026/10/29
========================================

一、這份ZIP已包含哪些東西
1. index.html、app.js、style.css：黑底五日族群輪動網站。
2. config/themes.json：18組自訂族群「固定代表股觀察籃」，並可切換「上市／上櫃官方大產業分類」。
3. scripts/update.py：證交所TWSE與櫃買TPEx兩市場盤後逐股資料、公司名冊，及上市／上櫃注意、處置公告快訊抓取。
4. scripts/publish.py：只輸出公開網頁及公開行情摘要；不包含XQ、RHEA主檔、個人交易紀錄。
5. .github/workflows/update.yml：GitHub Actions排程更新並部署GitHub Pages。
6. tests/test_update.py：日期／數字／不同市場schema／錯誤保護／模擬行情整合測試。
7. data/*：未取得實際官方行情前，保持「尚無資料」；沒有塞入任何假行情。
8. 本機預覽網站.bat：可在Windows開啟本機HTTP預覽（無網路抓取）。

二、怎樣讓它真正成為「自動更新的網址」？（需妳自己的GitHub帳號）
【請先建立新且公開的GitHub Repository，例如 rhea-taiwan-market；務必用 main 分支】

1. 登入 https://github.com/new
2. Repository name 填 rhea-taiwan-market；選 Public；建議先不要勾選README/License，建立空repo。
3. 在該repo按 Add file > Upload files，把這份ZIP解壓縮後『資料夾內的內容』上傳到repo根目錄。
   關鍵：確認 GitHub 能看到 index.html、app.js、style.css、scripts/update.py、
   config/themes.json，以及 .github/workflows/update.yml。
   如果網頁上傳漏掉隱藏的 .github 資料夾，必須用 GitHub Desktop 或另行補上該workflow，否則不能自動更新。
4. 在 GitHub Repository > Settings > Pages > Build and deployment > Source 選 GitHub Actions。
5. GitHub Repository > Actions > 選「RHEA 台股官方資料更新與網站發布」>
   按 Run workflow > main > Run workflow。
6. 進 Actions 看最近一次執行：測試是否通過、官方資料是否可下載、是否成功部署。
7. 成功後網站大致為 https://<GitHub帳號>.github.io/rhea-taiwan-market/
   以上是網址形式示例，不是目前已存在的網站。

若 GitHub 阻止workflow寫入：請確認 Settings > Actions > General > Workflow permissions 是否允許寫入，且repo/組織政策准許。若403：見下方。

三、更新時間與資料累積
- 台北時間工作日16:17、19:17以及次日07:17嘗試更新，實際GitHub可能延遲／漏跑。
- 股票行情API通常只給「最近一個交易日」，因此無法假裝第一天已有完整5日。
- 每次新日期經兩市場一致、資料完整度通過才存成 data/daily/YYYY-MM-DD.json。
- 公開網頁只顯示最近5個『已成功取得的實際交易日』，不足5日即標n/5。
- 重跑同一天只更新同一個日期檔，不多算交易日；網站會顯示來源實際日期。
- 歷史快照保存在repo data/daily/，前端只載入最近五天。

四、重要誠實性與資料品質限制
- v1.0已通過離線測試，但我們無法從目前工作環境連線官方API，GitHub正式雲端連線『尚未實測』。
- TPEx官方有可能阻擋GitHub雲端IP（HTTP 403）。若發生，網頁不會編造數字，而會保留先前成功的完整快照並顯示錯誤。此時要先做TPEx可用性排查，再考慮替代抓取環境；不可用其他市場的股票替代。
- 如果兩市場日期不同、欄位缺失、檔數太少，拒絕更新整張排行榜。
- 每日ROI計算是各股『當日收盤價相對參考價』漲跌幅，採算術等權；不是放空開盤到13:30、不是股價還原報酬。
- 除權息、特殊股本變更及非當日有成交的股票需要獨立核驗；股票年變動不代表未來操作優勢。
- 18組細分族群是預先固定的人工代表股名單，不是完整狹義產業分類；觀察籃成員可能因更換產業或更名需要人工調整。
- 官方注意／處置公告屬快照，不保證當下有效、或所有欄位皆可完整解析；務必點回官方公告核對起迄日。
- 本站不會讀取私人的RHEA Excel、下單程式、AUTO15或券商帳密，也沒有任何交易權。
- 公開repo裡的所有檔案與自訂族群名單通常都公開，請勿上傳私人交易或XQ設定。
- 在公開GitHub倉庫，若長期無活動，官方可能自動停用schedule；要定期檢查最近執行日。

五、Windows本機快速預覽／檢查
- 雙擊「本機預覽網站.bat」，瀏覽器會開 http://localhost:8765 。
- 還未有真實行情時只會顯示空資料，右上角可切到明確標示的虛構示意畫面。
- 本機要測試抓資料，在資料夾位置打開cmd輸入：py -3 scripts\update.py
  成功後用本機預覽查看；失敗請把完整cmd內容傳給RHEA，而不是手動改JSON數字。
- 如欲驗收程式：py -3 -m unittest discover -s tests -v
- 關閉本機預覽黑色視窗即可停掉HTTP伺服器。

六、GitHub部署驗收6條
[ ] Actions離線測試全部通過
[ ] 收盤資料TWSE、TPEx同一日期
[ ] 全市場上市/上櫃公司有效成交檔數合理（頁首顯示）
[ ] 自訂族群第一名可點開核對成員與漲幅
[ ] 五日新交易日正常累積，沒有用舊日當今天
[ ] 公告快訊日期與官方來源可追溯；未解析則標待核

七、版本管理
- 正式2.2、M v0.4、AUTO15、風控、額度、券商下單一律不由本站決定。
- 任何細分族群成員變動都需修 config/themes.json 的version；不追溯修改前期已保存的舊行情快照。
- 建議先驗收五日輪動穩定，才考慮另加融資、法人、D1/S3；後三者目前不是自動化驗收範圍。
