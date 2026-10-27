# Đăng nhập Codex và Antigravity

[English](LOGIN.md)

`/boss` gọi Codex và Antigravity ở chế độ chạy ngầm (headless), không có cửa sổ để hỏi đăng nhập. Vì vậy **anh phải đăng nhập mỗi công cụ một lần trước**. Thông tin đăng nhập được lưu lại trên máy, các lần sau tự dùng.

Tất cả lệnh dưới đây gõ trong **PowerShell** (Windows) hoặc **Terminal** (Mac/Linux). Nếu vừa cài công cụ xong, nhớ **mở cửa sổ terminal mới** để máy nhận lệnh.

---

## 1. Codex

### Cách thường dùng: đăng nhập bằng tài khoản ChatGPT

```
codex login
```

1. Trình duyệt tự mở trang đăng nhập OpenAI.
2. Đăng nhập tài khoản ChatGPT có quyền dùng Codex, rồi bấm cho phép.
3. Trình duyệt báo thành công, terminal quay lại dấu nhắc lệnh. Xong.

Kiểm tra:

```
codex login status
```

Nếu hiện tài khoản thì đã đăng nhập. Nếu hiện `Not logged in` thì làm lại bước trên.

### Máy không mở được trình duyệt (máy chủ, SSH, trình duyệt không tự bật)

```
codex login --device-auth
```

Terminal sẽ hiện một đường link và một mã. Anh mở link đó bằng trình duyệt ở **máy nào cũng được** (kể cả điện thoại), nhập mã, rồi đăng nhập.

### Dùng API key thay vì gói ChatGPT

Cách này tính tiền theo giá API, không dùng hạn mức của gói ChatGPT.

```powershell
# Windows PowerShell
$env:OPENAI_API_KEY = "sk-..."
$env:OPENAI_API_KEY | codex login --with-api-key
```

```bash
# Mac / Linux
printenv OPENAI_API_KEY | codex login --with-api-key
```

### Đăng xuất

```
codex logout
```

---

## 2. Antigravity (`agy`)

### Cách thường dùng: đăng nhập bằng tài khoản Google

```
agy
```

1. Lần đầu chạy, trình duyệt sẽ mở trang đăng nhập Google.
2. Đăng nhập tài khoản Google anh dùng cho Antigravity, rồi bấm cho phép.
3. Quay lại terminal, agy mở giao diện chat. Gõ `/exit` để thoát.

Từ giờ agy tự đăng nhập bằng phiên đã lưu, `/boss` gọi được ngay.

Nếu lần sau gõ `agy` mà nó vào thẳng giao diện chat, không mở trình duyệt, nghĩa là anh **đã đăng nhập rồi**.

### Máy không mở được trình duyệt (SSH, máy chủ)

Chạy `agy`. Terminal sẽ in ra một đường link đăng nhập. Anh copy link đó, mở bằng trình duyệt ở máy của mình, đăng nhập, rồi **dán mã hiện trên trình duyệt** ngược vào terminal.

### Dùng Gemini API key thay vì tài khoản Google

1. Mở (hoặc tạo) file `~/.gemini/antigravity-cli/settings.json`, thêm dòng:
   ```json
   { "modelProvider": "gemini" }
   ```
   Nếu file đã có nội dung, thêm `"modelProvider": "gemini"` vào trong cặp ngoặc `{ }` sẵn có.
2. Đặt biến môi trường `GEMINI_API_KEY`:
   ```powershell
   # Windows: đặt vĩnh viễn, mở terminal mới sau khi chạy
   setx GEMINI_API_KEY "AIza..."
   ```
   ```bash
   # Mac / Linux: thêm vào ~/.bashrc hoặc ~/.zshrc
   export GEMINI_API_KEY="AIza..."
   ```

Lưu ý: chỉ đặt `GEMINI_API_KEY` mà không có `modelProvider` thì **không có tác dụng**.

### Đăng xuất

Chạy `agy`, gõ `/logout`.

---

## 3. Kiểm tra cả hai cùng lúc

Sau khi đăng nhập xong, chạy:

```powershell
# Windows
py "$HOME\.claude\skills\boss\scripts\orch.py" doctor --live
```

```bash
# Mac / Linux
python3 ~/.claude/skills/boss/scripts/orch.py doctor --live
```

Kết quả đúng sẽ có hai dòng:

```
  [ok] codex: rc=0 6s
  [ok] agy: rc=0 22s
```

Lệnh này gọi thật mỗi công cụ một câu ngắn, không sửa file nào.

---

## Lỗi thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| `codex` / `agy` "is not recognized" | Chưa cài, hoặc chưa mở terminal mới sau khi cài. |
| `doctor` báo `[!!] codex` kèm lỗi 401 / unauthorized | Phiên đăng nhập hết hạn. Chạy lại `codex login`. |
| `doctor` báo `[!!] agy` kèm `authentication required` | Chưa đăng nhập agy ở chế độ có cửa sổ. Chạy `agy` một lần rồi đăng nhập. |
| Trình duyệt không tự mở | Codex: dùng `codex login --device-auth`. agy: copy link mà terminal in ra. |
| Đăng nhập rồi nhưng báo hết hạn mức (quota / rate limit) | Gói của anh đã dùng hết lượt trong khung giờ. Đợi hoặc nâng gói. Có thể giảm `max_parallel` trong `.orch/config.json` để đỡ tốn lượt. |
| Muốn đổi tài khoản | `codex logout` rồi `codex login`. Với agy thì `/logout` trong agy rồi chạy lại `agy`. |

> Thông tin đăng nhập nằm trên máy anh: Codex lưu ở `~/.codex/` hoặc trình quản lý mật khẩu của hệ điều hành, Antigravity lưu trong keyring của hệ điều hành. `/boss` không đọc, không sao chép và không gửi các thông tin này đi đâu. Nó chỉ gọi `codex` và `agy` như anh tự gõ lệnh.
