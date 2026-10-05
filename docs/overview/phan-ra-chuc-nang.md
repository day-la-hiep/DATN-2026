# Bảng phân rã chức năng

Phân rã chức năng của hệ thống Derma Hospital theo 3 cấp:
- **Cấp 1**: module.
- **Cấp 2**: nhóm chức năng.
- **Cấp 3**: chức năng chi tiết.

Cấp 1 số `n` tương ứng module `Mn` trong [requirements.md](requirements.md); trạng thái hiện tại xem ở tài liệu đó.

| Cấp 1 | Cấp 2 | Cấp 3 | Mô tả chi tiết |
|---|---|---|---|
| **1. Quản lý tài khoản** | 1.1 Xác thực | 1.1.1 Đăng ký tài khoản | Người dùng nhập tên đăng nhập, mật khẩu, họ tên, ngày sinh, giới tính. Hệ thống kiểm tra trùng tên đăng nhập, mã hoá mật khẩu, tạo tài khoản cùng một hồ sơ bệnh nhân mặc định cho chính chủ. |
| | | 1.1.2 Đăng nhập | Người dùng nhập tên đăng nhập và mật khẩu. Hệ thống xác thực, cấp phiên/token và chuyển tới màn hình theo vai trò (bệnh nhân → chat, bác sĩ → hàng đợi tư vấn). |
| | | 1.1.3 Đăng xuất | Huỷ phiên/token hiện tại, xoá dữ liệu phiên ở trình duyệt, quay về màn đăng nhập. |
| | 1.2 Tài khoản cá nhân | 1.2.1 Xem thông tin tài khoản | Hiển thị họ tên, ngày sinh, giới tính, vai trò; với bác sĩ hiển thị thêm phần giới thiệu chuyên môn. |
| | | 1.2.2 Cập nhật thông tin | Người dùng sửa thông tin cá nhân; bác sĩ sửa phần giới thiệu chuyên môn. |
| | | 1.2.3 Đổi mật khẩu | Nhập mật khẩu cũ và mật khẩu mới; hệ thống kiểm tra mật khẩu cũ rồi cập nhật. |
| | 1.3 Phân quyền | 1.3.1 Phân quyền theo vai trò | Mỗi tài khoản có vai trò bệnh nhân, bác sĩ hoặc quản trị. API và màn hình chỉ mở cho vai trò được phép (ví dụ chỉ bác sĩ được sửa bệnh án). |
| **2. Tư vấn với chatbot AI** | 2.1 Quản lý hội thoại | 2.1.1 Tạo hội thoại mới | Bệnh nhân chọn hồ sơ bệnh nhân và model AI, nhập câu hỏi đầu tiên. Hệ thống tạo hội thoại, lưu tin nhắn và bắt đầu lượt trả lời của chatbot. |
| | | 2.1.2 Xem danh sách hội thoại | Hiển thị các hội thoại của tài khoản, sắp theo thời gian cập nhật gần nhất, kèm tiêu đề tự sinh từ câu hỏi đầu. |
| | | 2.1.3 Xem lịch sử hội thoại | Tải lại toàn bộ tin nhắn của một hội thoại, gồm cả các bước lập luận và câu hỏi chatbot đang chờ trả lời. |
| | | 2.1.4 Đổi model AI | Chọn model khác cho hội thoại; áp dụng từ lượt hỏi kế tiếp, không ảnh hưởng lượt đang chạy. |
| | 2.2 Hỏi đáp | 2.2.1 Gửi câu hỏi / mô tả triệu chứng | Bệnh nhân nhập câu hỏi hoặc mô tả triệu chứng. Mỗi hội thoại xử lý một lượt tại một thời điểm, đang có lượt chạy thì không gửi thêm được. |
| | | 2.2.2 Nhận câu trả lời realtime | Câu trả lời được stream từng phần qua SSE; giao diện hiển thị dần nội dung, luôn kèm lưu ý "không phải chẩn đoán y khoa". |
| | | 2.2.3 Xem quá trình lập luận | Hiển thị các bước chatbot đã suy nghĩ và các công cụ đã dùng (tra guideline, tra KG, phân loại ảnh...) cùng kết quả của từng công cụ. |
| | | 2.2.4 Trả lời câu hỏi bổ sung của chatbot | Khi thiếu thông tin, chatbot tạm dừng và hỏi lại kèm các lựa chọn. Bệnh nhân chọn một phương án, tự nhập hoặc bỏ qua; chatbot tiếp tục đúng chỗ đã dừng. |
| | | 2.2.5 Xem nguồn tham khảo | Mỗi câu trả lời kèm danh sách nguồn (guideline, sách, trang web uy tín) mà chatbot đã dùng làm căn cứ. |
| | 2.3 Hỗ trợ tiền chẩn đoán | 2.3.1 Gửi ảnh vùng da | Bệnh nhân đính kèm ảnh vào tin nhắn; ảnh được tải lên kho lưu trữ trước khi gửi. |
| | | 2.3.2 Phân loại bệnh qua ảnh | Mô hình CNN (22 lớp bệnh) dự đoán bệnh từ ảnh kèm độ tin cậy; kết quả chỉ là giả thuyết để chatbot đối chiếu với triệu chứng. |
| | | 2.3.3 Chẩn đoán phân biệt | Từ mô tả triệu chứng, chatbot chuẩn hoá thuật ngữ, tìm bệnh ứng viên trên KG, tra guideline từng bệnh, xếp hạng và đề xuất câu hỏi phân biệt tiếp theo. |
| | | 2.3.4 Cảnh báo dấu hiệu nguy hiểm | Khi phát hiện dấu hiệu cần khám ngay, chatbot khuyến nghị bệnh nhân đi khám hoặc yêu cầu tư vấn bác sĩ. |
| | 2.4 Tra cứu tri thức | 2.4.1 Tra cứu thông tin bệnh lý | Chatbot tra guideline (BYT, WHO, MedlinePlus), sách đã số hoá và web uy tín để trả lời về nguyên nhân, triệu chứng, điều trị, phòng ngừa. |
| | | 2.4.2 Tra cứu ca bệnh liên quan | Tìm các ca bệnh đã được bác sĩ xác nhận có triệu chứng / hình ảnh tương tự để tham khảo. |
| | 2.5 Ghi nhớ bệnh nhân | 2.5.1 Lưu thông tin quan trọng | Chatbot tự lưu thông tin đáng nhớ (tiền sử, dị ứng, thuốc đang dùng...) của bệnh nhân. |
| | | 2.5.2 Sử dụng lại thông tin đã nhớ | Ở các lượt và hội thoại sau, chatbot tự tìm lại thông tin liên quan để không phải hỏi lại. |
| **3. Tổng hợp thông tin lâm sàng** | 3.1 Clinical fact | 3.1.1 Trích xuất clinical fact | Từ hội thoại với chatbot, hệ thống trích các dữ kiện lâm sàng có cấu trúc: triệu chứng, vị trí, thời gian khởi phát, tiến triển, tiền sử, thuốc, dị ứng, kết quả phân loại ảnh. |
| | | 3.1.2 Liên kết tin nhắn nguồn | Mỗi clinical fact lưu kèm các tin nhắn gốc làm bằng chứng để bác sĩ kiểm chứng. |
| | | 3.1.3 Cập nhật clinical fact | Khi bệnh nhân bổ sung hoặc đính chính thông tin, fact cũ được cập nhật hoặc đánh dấu thay thế, không xoá lịch sử. |
| | 3.2 Báo cáo tiền tư vấn | 3.2.1 Sinh báo cáo tổng hợp | Khi bệnh nhân yêu cầu tư vấn bác sĩ, hệ thống tổng hợp clinical fact, giả thuyết chẩn đoán phân biệt và nguồn KB thành một báo cáo ngắn. |
| | | 3.2.2 Xem báo cáo | Bác sĩ xem báo cáo trước khi nhận ca, mở từng kết luận để xem nguồn lập luận từ KB và tin nhắn nguồn. |
| **4. Tư vấn trực tiếp với bác sĩ** | 4.1 Yêu cầu tư vấn | 4.1.1 Gửi yêu cầu tư vấn | Từ một hội thoại, bệnh nhân gửi yêu cầu kèm lý do; hệ thống tạo phiên tư vấn ở trạng thái chờ và chèn tin mốc vào luồng chat. |
| | | 4.1.2 Tiếp tục hỏi chatbot khi chờ | Trong lúc chưa có bác sĩ nhận, bệnh nhân vẫn hỏi chatbot bình thường trong cùng hội thoại. |
| | | 4.1.3 Huỷ yêu cầu | Bệnh nhân huỷ yêu cầu khi chưa có bác sĩ nhận. |
| | 4.2 Tiếp nhận ca | 4.2.1 Xem hàng đợi yêu cầu | Bác sĩ xem danh sách yêu cầu đang chờ kèm lý do và báo cáo tóm tắt. |
| | | 4.2.2 Nhận ca | Bác sĩ nhận một yêu cầu; phiên chuyển sang đang tư vấn, bệnh nhân được thông báo. |
| | | 4.2.3 Kết thúc ca | Bác sĩ đánh dấu đã xử lý xong; phiên đóng, có tin mốc kết thúc trong luồng chat. |
| | 4.3 Trao đổi | 4.3.1 Chat với bệnh nhân | Bác sĩ và bệnh nhân nhắn tin realtime trong cùng hội thoại; tin của bác sĩ được phân biệt rõ với tin của chatbot. |
| | | 4.3.2 Video call | Một bên mở cuộc gọi video trong phiên tư vấn; hệ thống ghi lại thời điểm bắt đầu / kết thúc cuộc gọi vào luồng chat. |
| | | 4.3.3 Xem thông tin hỗ trợ khi trao đổi | Trong lúc tư vấn, bác sĩ xem song song clinical fact, báo cáo và truy xuất tin nhắn nguồn cho từng kết luận. |
| **5. Đặt lịch khám** | 5.1 Lịch bác sĩ | 5.1.1 Khai báo lịch làm việc | Bác sĩ khai báo các khung giờ có thể khám. |
| | | 5.1.2 Xem lịch hẹn | Bác sĩ xem danh sách lịch hẹn theo ngày / tuần. |
| | 5.2 Lịch bệnh nhân | 5.2.1 Đặt lịch khám | Bệnh nhân chọn bác sĩ và khung giờ trống, chọn hồ sơ bệnh nhân, nhập lý do khám. |
| | | 5.2.2 Xem / huỷ / đổi lịch | Bệnh nhân xem lịch đã đặt, huỷ hoặc chuyển sang khung giờ khác; hai bên đều được cập nhật. |
| **6. Hồ sơ bệnh nhân & bệnh án** | 6.1 Hồ sơ bệnh nhân | 6.1.1 Quản lý hồ sơ | Một tài khoản tạo / sửa / xoá nhiều hồ sơ bệnh nhân (bản thân, người nhà), mỗi hồ sơ có họ tên, ngày sinh, giới tính. |
| | | 6.1.2 Xem lịch sử khám | Xem các lượt tư vấn và bệnh án theo từng hồ sơ, sắp theo thời gian. |
| | | 6.1.3 Xem thư viện ảnh | Xem tập trung các ảnh bệnh đã gửi theo từng hồ sơ, kèm thời điểm và kết quả phân loại. |
| | 6.2 Bệnh án | 6.2.1 Bác sĩ xem hồ sơ bệnh nhân | Bác sĩ xem hồ sơ, lịch sử bệnh án và ảnh của bệnh nhân mình đang tư vấn. |
| | | 6.2.2 Cập nhật bệnh án | Sau mỗi lượt khám, bác sĩ ghi chẩn đoán, ghi chú, hướng điều trị vào bệnh án của hồ sơ. |
| | | 6.2.3 Bệnh nhân xem bệnh án | Bệnh nhân xem bệnh án do bác sĩ ghi (chỉ đọc). |
| **7. Quản lý ca bệnh & dữ liệu ảnh** | 7.1 Ca bệnh | 7.1.1 Lưu ca bệnh | Bác sĩ lưu một ca đã xác nhận gồm chẩn đoán, mô tả lâm sàng và ảnh, ẩn thông tin định danh bệnh nhân. |
| | | 7.1.2 Đưa ca bệnh vào KB | Ca bệnh đã xác nhận được nạp vào kho tri thức để chatbot tra cứu ca tương tự. |
| | 7.2 Dữ liệu ảnh | 7.2.1 Xác nhận nhãn ảnh | Bác sĩ xác nhận hoặc sửa nhãn bệnh của ảnh (theo danh mục lớp của CNN). |
| | | 7.2.2 Xuất bộ dữ liệu huấn luyện | Xuất các ảnh đã xác nhận nhãn thành bộ dữ liệu phục vụ huấn luyện lại mô hình CNN. |
| **8. Knowledge Graph** | 8.1 Khai thác KG | 8.1.1 Truy vấn KG | Chatbot hỏi đáp quan hệ bệnh – triệu chứng – thuốc – gen trên PrimeKG (lọc da liễu). |
| | | 8.1.2 Chuẩn hoá thuật ngữ | Ánh xạ thuật ngữ bệnh nhân dùng sang thuật ngữ chuẩn của ontology DermO. |
| | 8.2 Trực quan hoá | 8.2.1 Xem KG liên quan bệnh nhân | Bác sĩ xem đồ thị con quanh các triệu chứng / bệnh ứng viên của bệnh nhân (lấy từ clinical fact). |
| | | 8.2.2 Tương tác với đồ thị | Phóng to, lọc theo loại quan hệ, bấm vào nút để xem chi tiết thực thể và guideline liên quan. |
| **9. Quản lý Knowledge Base** | 9.1 Tài liệu | 9.1.1 Tải lên tài liệu | Bác sĩ tải lên giáo trình / guideline dạng PDF (tối đa 500 MB), đặt tiêu đề và cách đọc chữ (lớp text có sẵn hoặc OCR). |
| | | 9.1.2 Xem danh sách / xoá tài liệu | Xem các tài liệu kèm trạng thái xử lý; xoá tài liệu sẽ xoá cả file và dữ liệu đã nạp vào KB. |
| | | 9.1.3 Cấu hình xử lý | Chỉnh tham số xử lý của từng tài liệu (engine đọc chữ, độ dài đoạn, cấp mục làm ranh giới). |
| | 9.2 Số hoá tài liệu | 9.2.1 Đọc nội dung | Chuyển PDF thành chữ theo từng trang, tách header và số trang in; có thể dừng và chạy tiếp. |
| | | 9.2.2 Đọc mục lục | AI đọc các trang mục lục thành cây phần – chương – mục kèm số trang, tự gắn vào trang thật và đánh dấu các mục nghi ngờ. |
| | | 9.2.3 Duyệt và sửa mục lục | Người duyệt sửa tên / cấp / số trang, thêm hoặc xoá mục, chỉnh độ lệch trang; bản sửa lưu riêng, không mất khi chạy lại AI. |
| | | 9.2.4 Chia đoạn | Cắt nội dung thành các đoạn trong khung mục lục, mỗi đoạn mang thông tin phần / chương / mục / trang; đoạn bất thường được đưa vào hàng xem lại. |
| | | 9.2.5 Nạp vào kho tri thức | Tạo embedding cho từng đoạn và nạp vào cơ sở dữ liệu vector; chạy lại sẽ thay toàn bộ dữ liệu cũ của tài liệu. |
| | | 9.2.6 Theo dõi và duyệt từng bước | Mỗi bước chạy nền, hiển thị tiến độ và nhật ký; phải được duyệt thì bước sau mới chạy, chạy lại một bước làm các bước sau phải chạy lại. |
| | 9.3 Khai thác KB | 9.3.1 Chatbot tra tài liệu đã nạp | Chatbot tìm các đoạn liên quan trong tài liệu đã nạp và trích dẫn đúng sách / mục / trang. |
| | | 9.3.2 Làm giàu KB cùng chatbot | Bác sĩ dùng chatbot để tra cứu, phát hiện thiếu sót và đề xuất bổ sung tri thức vào KB; nội dung bổ sung phải được bác sĩ duyệt. |
