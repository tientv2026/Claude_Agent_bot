# agent-boss

**Claude Code làm sếp. Codex và Antigravity cùng code song song.**

[English](README.md)

Anh gõ `/boss <việc cần làm>` trong Claude Code. Claude đọc dự án, chia việc thành nhiều task, mỗi task phụ trách một nhóm file riêng, rồi giao cho **Codex CLI** và **Antigravity CLI** (`agy`) code cùng lúc. Mỗi task chạy trong một git worktree riêng. Xong việc, Claude review từng diff: chỗ nào chưa đạt thì trả về kèm góp ý, chỗ nào ổn thì merge.

## Vì sao nên dùng

- **Song song**: backend và frontend được hai agent làm cùng lúc.
- **An toàn**: worker không đụng vào thư mục code chính của anh. Mọi thay đổi nằm ở branch riêng, phải qua master review mới được merge.
- **Dùng gói có sẵn**: Codex chạy bằng gói ChatGPT, Antigravity chạy bằng gói Google AI. Công cụ này không cần API key.
- **Không cần cài thêm thư viện**: chỉ một file Python dùng thư viện chuẩn, chạy được trên Windows, macOS và Linux.

## Cần có

- [Claude Code](https://code.claude.com), dùng bản CLI hoặc app desktop. Trên app desktop phải chọn môi trường **Local**.
- [Codex CLI](https://github.com/openai/codex): `npm i -g @openai/codex`, sau đó chạy `codex login`.
- [Antigravity CLI](https://antigravity.google/docs/getting-started): cài `agy`, rồi gõ `agy` một lần để đăng nhập.
- Git và Python 3.9 trở lên.

Có một worker cũng chạy được, master sẽ chỉ giao việc cho worker mà lệnh `doctor` tìm thấy.

Nếu máy Windows chưa cài gì: chạy `install/setup-windows.ps1`, script sẽ cài Git, Python, Node và Codex bằng winget.

## Cài đặt

**Cách A: cài dạng plugin của Claude Code** (cập nhật bằng lệnh `claude plugin update`)

```bash
claude plugin marketplace add tientv2026/Claude_Agent_bot
claude plugin install agent-boss@agent-boss
```

**Cách B: cài bằng một dòng lệnh**

```powershell
# Windows PowerShell
irm https://raw.githubusercontent.com/tientv2026/Claude_Agent_bot/main/install/install.ps1 | iex
```

```bash
# macOS / Linux / WSL
curl -fsSL https://raw.githubusercontent.com/tientv2026/Claude_Agent_bot/main/install/install.sh | bash
```

**Kiểm tra worker có trả lời thật không** (lệnh này gọi thật mỗi bên một lần):

```powershell
py "$HOME\.claude\skills\boss\scripts\orch.py" doctor --live
```

## Cách dùng

Mở thư mục dự án trong Claude Code. Thư mục phải là git repo, nếu chưa phải thì Claude sẽ tự `git init`. Sau đó gõ:

```
/boss làm form liên hệ: endpoint REST bằng PHP có giới hạn số lần gửi, giao diện Tailwind responsive
```

Nếu cài dạng plugin thì lệnh là `/agent-boss:boss`. Gõ `/boss` cũng được nếu không có lệnh nào khác trùng tên.

Muốn chia việc theo ý mình thì cứ nói thẳng, ví dụ: *"codex lo backend, agy lo hết UI"*.

Các bước master làm: lập kế hoạch trong `.orch/plan.json`, giao việc song song, review, merge, rồi chạy đợt tiếp theo nếu có task phụ thuộc. Cuối cùng master báo lại ai đã làm gì và những chỗ anh cần tự kiểm tra. Kế hoạch mẫu cho WordPress xem ở [examples/plan.example.json](examples/plan.example.json).

## Cấu hình và xử lý lỗi

Phần cấu hình, danh sách lệnh và cách xử lý lỗi có đủ trong [README tiếng Anh](README.md#configuration).

Vài lưu ý nhanh:
- Task của agy bị `timeout`: cập nhật agy lên bản mới. Trong lúc chờ, chạy `retry <id> --agent codex` để chuyển task đó sang Codex.
- Windows báo `Python was not found`: đó là lối tắt mở Microsoft Store, không phải Python thật. Cài Python bằng `winget install -e --id Python.Python.3.12`.
- Nên đặt repo ở thư mục theme hoặc plugin, không đặt ở cả `wp-content`. Không để `wp-config.php` hay key bí mật trong repo.

## Giấy phép

MIT
