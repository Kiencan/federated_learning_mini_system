// Sinh báo cáo cuối kỳ DOCX — Federated Learning Mini System
// Chạy: node generate_docx.js  →  Report/bao_cao_cuoi_ky.docx
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun,
  AlignmentType, LevelFormat, TableOfContents, HeadingLevel, BorderStyle,
  WidthType, ShadingType, PageBreak, Footer, PageNumber, VerticalAlign,
} = require("docx");

const FIG = (name) => path.join(__dirname, "Report", "figures", name);
const CONTENT_W = 9360; // US Letter, 1" margins

// ---------- helpers ----------
const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const H3 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(t)] });

function P(text, opts = {}) {
  return new Paragraph({
    spacing: { after: 120, line: 276 },
    alignment: opts.justify ? AlignmentType.JUSTIFIED : undefined,
    children: [new TextRun({ text, bold: opts.bold, italics: opts.italics })],
  });
}

// Paragraph với nhiều run (bold inline) — runs = [{t, bold, italics}]
function PR(runs, opts = {}) {
  return new Paragraph({
    spacing: { after: 120, line: 276 },
    alignment: opts.justify ? AlignmentType.JUSTIFIED : undefined,
    children: runs.map((r) => new TextRun({ text: r.t, bold: r.bold, italics: r.italics })),
  });
}

function bullet(text, runs) {
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { after: 80, line: 276 },
    children: runs
      ? runs.map((r) => new TextRun({ text: r.t, bold: r.bold, italics: r.italics }))
      : [new TextRun(text)],
  });
}

const border = { style: BorderStyle.SINGLE, size: 1, color: "B0B7C3" };
const borders = { top: border, bottom: border, left: border, right: border,
  insideHorizontal: border, insideVertical: border };

function cell(text, w, { head = false, bold = false, align } = {}) {
  return new TableCell({
    borders,
    width: { size: w, type: WidthType.DXA },
    shading: { fill: head ? "1F4E79" : "FFFFFF", type: ShadingType.CLEAR },
    margins: { top: 60, bottom: 60, left: 110, right: 110 },
    verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({
      alignment: align,
      children: [new TextRun({ text, bold: head || bold, color: head ? "FFFFFF" : "000000", size: 20 })],
    })],
  });
}

// rows: [[c1,c2,...], ...]; widths: [w1,w2,...]; firstRowHead
function table(widths, rows, { headRow = true } = {}) {
  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: widths,
    rows: rows.map((r, ri) =>
      new TableRow({
        tableHeader: headRow && ri === 0,
        children: r.map((c, ci) =>
          cell(String(c), widths[ci], {
            head: headRow && ri === 0,
            align: ci === 0 ? AlignmentType.LEFT : AlignmentType.CENTER,
          })),
      })),
  });
}

function figure(file, ratio, caption, wPx = 600) {
  const hPx = Math.round(wPx / ratio);
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 120, after: 60 },
      children: [new ImageRun({
        type: "png",
        data: fs.readFileSync(file),
        transformation: { width: wPx, height: hPx },
        altText: { title: caption, description: caption, name: caption },
      })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 200 },
      children: [new TextRun({ text: caption, italics: true, size: 19, color: "555555" })],
    }),
  ];
}

const spacer = () => new Paragraph({ children: [new TextRun("")], spacing: { after: 60 } });

// ============================================================
// NỘI DUNG
// ============================================================
const body = [];

// ---- TRANG BÌA ----
body.push(
  new Paragraph({ spacing: { before: 2400, after: 200 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: "BÁO CÁO CUỐI KỲ", bold: true, size: 56, color: "1F4E79" })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 },
    children: [new TextRun({ text: "Hệ phân tán — Distributed Systems", size: 28, color: "555555" })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 600, after: 200 },
    children: [new TextRun({ text: "FEDERATED LEARNING MINI SYSTEM", bold: true, size: 40 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 },
    children: [new TextRun({ text: "Huấn luyện phân tán MNIST trên 2 node với gRPC + FedAvg", size: 24, italics: true })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 1800, after: 80 },
    children: [new TextRun({ text: "Trọng tâm: 5 vấn đề Distributed Systems", size: 24, bold: true })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 },
    children: [new TextRun({ text: "Communication · Synchronization · Straggler · Fault Tolerance · Data Heterogeneity", size: 20, color: "555555" })] }),
  new Paragraph({ children: [new PageBreak()] }),
);

// ---- MỤC LỤC ----
body.push(
  H1("Mục lục"),
  new TableOfContents("Mục lục", { hyperlink: true, headingStyleRange: "1-2" }),
  new Paragraph({ children: [new PageBreak()] }),
);

// ---- 1. TỔNG QUAN ----
body.push(H1("1. Tổng quan hệ thống"));
body.push(P("Hệ thống Federated Learning 2-node huấn luyện phân tán mô hình phân loại chữ số viết tay MNIST mà không tập trung dữ liệu thô: mỗi client giữ shard dữ liệu riêng, chỉ gửi tham số mô hình (state_dict) về server để tổng hợp. Đây là kiến trúc bảo vệ quyền riêng tư dữ liệu, đồng thời là môi trường lý tưởng để khảo sát các vấn đề cốt lõi của hệ phân tán.", { justify: true }));
body.push(table(
  [2400, 6960],
  [
    ["Thành phần", "Mô tả"],
    ["Hardware", "Máy 1 (Server + Client-0, GPU RTX 2000 Ada) + Máy 2 (Client-1, GPU RTX 2000 Ada), kết nối qua mạng LAN"],
    ["Mô hình", "CNN nhỏ: 2 lớp conv (32, 64 filters) + 2 lớp FC + dropout; state_dict serialized 1.611 MiB"],
    ["Thuật toán", "FedAvg — trung bình có trọng số theo số mẫu (num_samples) của mỗi client"],
    ["Giao thức", "gRPC + Protocol Buffers, cổng 50051"],
    ["State machine", "TRAINING → AGGREGATING → EVALUATING → (round kế tiếp | DONE)"],
    ["Đồng bộ", "Bounded synchronous: chờ tối đa WAIT_TIMEOUT, tổng hợp khi đủ MIN_CLIENTS"],
  ],
));
body.push(spacer());
body.push(PR([
  { t: "3 RPC chính: " , bold: true },
  { t: "GetGlobalModel" , bold: true },
  { t: " (client kéo mô hình hiện tại), " },
  { t: "SubmitUpdate" , bold: true },
  { t: " (client gửi update, qua 4 lớp validation: unknown_client → state_not_training → stale_round → duplicate), " },
  { t: "GetRoundStatus" , bold: true },
  { t: " (client poll trạng thái round)." },
], { justify: true }));
body.push(P("Chi tiết kiến trúc và quá trình triển khai 7 milestone được trình bày trong milestone_report.md.", { italics: true }));

// ---- 2. THIẾT LẬP ----
body.push(H1("2. Thiết lập thí nghiệm"));
body.push(H2("2.1 Siêu tham số đồng nhất"));
body.push(P("Mọi thí nghiệm dùng chung bộ siêu tham số để đảm bảo so sánh công bằng và tái lập được:", { justify: true }));
body.push(table(
  [4680, 4680],
  [
    ["Tham số", "Giá trị"],
    ["local_epochs", "2"],
    ["batch_size", "32"],
    ["learning_rate", "0.01"],
    ["seed", "42 (random, numpy, torch)"],
    ["optimizer", "SGD (momentum = 0.9)"],
    ["model size", "1.611 MiB (state_dict)"],
  ],
));
body.push(spacer());
body.push(H2("2.2 Phân vai trò dữ liệu (quan trọng để diễn giải đúng)"));
body.push(bullet(null, [{ t: "Accuracy / convergence: ", bold: true }, { t: "dùng baseline 20 round/epoch chạy localhost trên Máy 1 (Experiment 1 và 2). Mạng không ảnh hưởng accuracy." }]));
body.push(bullet(null, [{ t: "Timing / wall-clock: ", bold: true }, { t: "lấy từ các run cross-machine thật (m44_cross cho normal federated; m76_f1_v3 cho fault). Localhost 2 client tranh cùng GPU nên wall-clock không phản ánh hệ thật, KHÔNG dùng làm kết luận performance." }]));
body.push(H2("2.3 Phân hoạch dữ liệu"));
body.push(bullet(null, [{ t: "IID: ", bold: true }, { t: "mỗi client 30.000 mẫu, phân phối lớp đều (~3.000/lớp)." }]));
body.push(bullet(null, [{ t: "Non-IID pathological: ", bold: true }, { t: "Client-0 chỉ thấy digit 0–4 (30.596 mẫu), Client-1 chỉ thấy 5–9 (29.404 mẫu) — kịch bản lệch phân phối cực đoan." }]));

// ---- 3. EXP 1 ----
body.push(new Paragraph({ children: [new PageBreak()] }));
body.push(H1("3. Experiment 1 — Centralized vs Federated"));
body.push(P("So sánh mô hình huấn luyện tập trung (gom toàn bộ 60.000 mẫu về một máy) với Federated IID, nhằm trả lời câu hỏi: việc phân tán có làm giảm chất lượng mô hình không?", { justify: true }));
body.push(table(
  [3360, 2000, 2000, 2000],
  [
    ["Setup", "Final acc", "avg 1-5", "rounds→98%"],
    ["Centralized (20 epoch)", "99.29%", "98.81%", "1"],
    ["Federated IID (20 round)", "99.38%", "99.06%", "1"],
  ],
));
body.push(spacer());
body.push(...figure(FIG("accuracy_per_round.png"), 1.6, "Hình 1. Accuracy theo round/epoch — IID vs Non-IID vs Centralized"));
body.push(H2("Nhận xét"));
body.push(bullet(null, [{ t: "Ngang bằng accuracy: ", bold: true }, { t: "Federated IID đạt 99.38%, xấp xỉ centralized 99.29%. Với dữ liệu IID, FedAvg gần như tương đương gradient descent tập trung — việc phân tán không làm giảm chất lượng mô hình." }]));
body.push(bullet(null, [{ t: "Chi phí của phân tán ", bold: true }, { t: "nằm ở communication (mục 7.1) và độ phức tạp đồng bộ (mục 7.2), không phải ở accuracy." }]));
body.push(bullet(null, [{ t: "Wall-clock: ", bold: true }, { t: "centralized 20 epoch = 156,7s (cục bộ). Federated cross-machine steady-state ~12,7s/round. Hai mô hình khác bản chất đo (epoch toàn bộ dữ liệu vs round với local epochs + mạng) nên KHÔNG so sánh trực tiếp tổng wall-clock như kết luận performance." }]));

// ---- 4. EXP 2 ----
body.push(new Paragraph({ children: [new PageBreak()] }));
body.push(H1("4. Experiment 2 — IID vs Non-IID (Data Heterogeneity)"));
body.push(P("Cùng cấu hình, chỉ thay đổi cách phân hoạch dữ liệu giữa 2 client.", { justify: true }));
body.push(table(
  [3360, 2000, 2000, 2000],
  [
    ["Setup", "Final acc", "avg 1-5", "rounds→98%"],
    ["Federated IID", "99.38%", "99.06%", "1"],
    ["Federated Non-IID", "98.33%", "96.04%", "5"],
  ],
));
body.push(spacer());
body.push(PR([
  { t: "Đường hội tụ (Hình 1): " , bold: true },
  { t: "Non-IID khởi đầu chỉ 92,17% ở round 1 (so với IID 98,52%), cần 5 round mới vượt 98%, và plateau ở mức thấp hơn (~98,5% so với ~99,4%)." },
], { justify: true }));
body.push(...figure(FIG("per_class_accuracy_iid_vs_noniid.png"), 1.8, "Hình 2. Per-class accuracy ở round cuối — IID vs Non-IID"));
body.push(H2("Nhận xét"));
body.push(bullet(null, [{ t: "Hội tụ chậm hơn rõ rệt: ", bold: true }, { t: "avg_acc_first_5 thấp hơn IID 3 điểm % (96,04 vs 99,06). Mỗi client chỉ thấy nửa số lớp nên mô hình cục bộ bị kéo về hướng riêng (client gradient divergence), FedAvg cần nhiều round hơn để dung hoà." }]));
body.push(bullet(null, [{ t: "Lệch per-class: ", bold: true }, { t: "ở round cuối, Non-IID kém nhất tại class 3 (95,0%) và class 9 (96,3%), trong khi IID đều ~99% mọi lớp. Đây là dấu hiệu đặc trưng của data heterogeneity mà accuracy tổng (98,33%) che giấu một phần." }]));
body.push(bullet(null, [{ t: "Kết luận: ", bold: true }, { t: "dữ liệu không đồng đều giữa các node làm chậm hội tụ và giảm accuracy cuối — vấn đề chỉ tồn tại trong Federated; centralized không gặp vì đã gom dữ liệu." }]));

// ---- 5. EXP 3 ----
body.push(new Paragraph({ children: [new PageBreak()] }));
body.push(H1("5. Experiment 3 — Straggler Problem"));
body.push(P("Inject delay nhân tạo (cờ --straggler-delay) vào client trước khi SubmitUpdate, mô phỏng client chậm. Đo trên 2 kịch bản đối lập.", { justify: true }));
body.push(table(
  [2600, 1300, 1700, 1860, 1900],
  [
    ["Kịch bản", "delay", "wait_timeout", "Kết quả", "wallclock/round"],
    ["S1 — Timeout đủ rộng", "5s", "60s", "3/3 round ok (đủ 2 client)", "~15s"],
    ["S2 — Timeout chặt", "20s", "20s", "3/3 round partial (drop)", "~21s"],
  ],
));
body.push(spacer());
body.push(H2("Nhận xét"));
body.push(bullet(null, [{ t: "S1: ", bold: true }, { t: "straggler chậm 5s nhưng server chờ được → mọi round vẫn ok, accuracy 99,17%. round_wallclock tăng đúng ~5s/round. Cả round bị kéo chậm theo client chậm nhất — bản chất của bounded synchronous." }]));
body.push(bullet(null, [{ t: "S2: ", bold: true }, { t: "timeout (20s) ngắn hơn thời gian straggler (8s train + 20s sleep = 28s) → server bỏ qua straggler, aggregate với 1 client (partial). round_wallclock ≈ 21s = wait_timeout. Accuracy giảm nhẹ (98,85% vs 99,17%)." }]));
body.push(bullet(null, [{ t: "Tradeoff cốt lõi: ", bold: true }, { t: "chờ straggler → round chậm nhưng accuracy cao; drop straggler → round nhanh/đều nhưng accuracy giảm. WAIT_TIMEOUT là tham số điều chỉnh tradeoff này." }]));

// ---- 6. EXP 4 ----
body.push(new Paragraph({ children: [new PageBreak()] }));
body.push(H1("6. Experiment 4 — Fault Tolerance (Crash + Reconnect)"));
body.push(P("Cross-machine 16 round (m76_f1_v3). Thao tác thủ công Ctrl+C Client-1 trên Máy 2 giữa run, sau đó khởi động lại — mô phỏng crash + reconnect.", { justify: true }));
body.push(table(
  [3000, 1700, 2800, 1860],
  [
    ["Phase", "Round", "Trạng thái", "Accuracy"],
    ["Cold start", "1-2", "partial (Client-1 chưa join)", "98.3%"],
    ["Healthy", "3-7", "ok (cả 2 client)", "99.22-99.36%"],
    ["Degraded (Ctrl+C)", "8-11", "partial (chỉ Client-0)", "99.07-99.24%"],
    ["Recovery (restart)", "12-16", "ok (Client-1 rejoin)", "99.28-99.41%"],
  ],
));
body.push(spacer());
body.push(PR([
  { t: "Bằng chứng từ log: " , bold: true },
  { t: "events.csv ghi update_received của Client-1 ở round 3–7, rồi gap round 7→12 (~3 phút) đúng cửa sổ crash, rồi tiếp tục round 12–16. Server không hề dừng suốt giai đoạn degraded — tiếp tục aggregate với 1 client (partial_aggregation, round_wallclock ≈ 46s = wait_timeout)." },
], { justify: true }));
body.push(H2("Nhận xét"));
body.push(bullet(null, [{ t: "Chịu lỗi: ", bold: true }, { t: "1 client crash không làm sập hệ thống nhờ MIN_CLIENTS=1 + WAIT_TIMEOUT → fallback partial aggregation." }]));
body.push(bullet(null, [{ t: "Không degrade accuracy: ", bold: true }, { t: "sau recovery, accuracy đạt đỉnh 99,41% — mô hình không bị hỏng bởi chu trình crash/recovery." }]));
body.push(bullet(null, [{ t: "Observability: ", bold: true }, { t: "mọi sự kiện được log rõ ràng (round_timeout, partial_aggregation, update_received) — đáp ứng yêu cầu của đề bài." }]));

// ---- 7. PHÂN TÍCH 5 VẤN ĐỀ ----
body.push(new Paragraph({ children: [new PageBreak()] }));
body.push(H1("7. Phân tích 5 vấn đề Distributed Systems"));

body.push(H2("7.1 Communication Overhead"));
body.push(...figure(FIG("communication_overhead.png"), 1.6, "Hình 3. Communication overhead tích luỹ (MiB)"));
body.push(table(
  [4680, 4680],
  [
    ["Đại lượng", "Giá trị"],
    ["model_size", "1.611 MiB (state_dict serialized)"],
    ["comm/round", "1.611 × 2 chiều × 2 client = 6.44 MiB"],
    ["20 round", "128.9 MiB"],
  ],
));
body.push(spacer());
body.push(bullet(null, [{ t: "Tuyến tính theo round và số client: ", bold: true }, { t: "với mô hình lớn hơn (ResNet, BERT), con số này bùng nổ → đây là nút thắt chính của Federated Learning thực tế." }]));
body.push(...figure(FIG("round_time_breakdown.png"), 1.6, "Hình 4. Round time breakdown (coarse, steady-state) — normal federated"));
body.push(bullet(null, [{ t: "Breakdown thời gian round (steady-state): ", bold: true }, { t: "phần lớn là client train + communication (~11,7s), evaluation ~0,98s, aggregation chỉ ~2,1ms (gần như vô hình). Round time bị chi phối bởi client compute + truyền mô hình, không phải xử lý server-side." }]));
body.push(bullet(null, [{ t: "gRPC/protobuf vs HTTP+JSON: ", bold: true }, { t: "protobuf serialize binary trực tiếp từ state_dict bytes, không text parsing. JSON phải base64-encode tensor (~+33% kích thước) + parse text → chậm và tốn băng thông hơn. gRPC còn dùng HTTP/2 multiplexing." }]));
body.push(bullet(null, [{ t: "Future Work: ", bold: true }, { t: "weight delta, top-k sparsification, int8 quantization (giảm ~4× kích thước) — đánh đổi accuracy/độ phức tạp." }]));

body.push(H2("7.2 Synchronization Model"));
body.push(P("Hệ dùng bounded synchronous:", {}));
body.push(bullet(null, [{ t: "Có timeout ", bold: true }, { t: "→ không bị block vô hạn bởi client treo (khác synchronous thuần)." }]));
body.push(bullet(null, [{ t: "Vẫn chờ đủ MIN_CLIENTS ", bold: true }, { t: "trước khi aggregate (khác asynchronous hoàn toàn)." }]));
body.push(bullet(null, [{ t: "Tradeoff (minh chứng bằng Exp 3): ", bold: true }, { t: "WAIT_TIMEOUT lớn → chờ được straggler, accuracy cao nhưng round chậm; nhỏ → round nhanh/đều nhưng drop straggler, accuracy giảm." }]));
body.push(bullet(null, [{ t: "Background aggregation thread + 3-phase lock ", bold: true }, { t: "(snapshot → heavy work no-lock → guarded commit) đảm bảo correctness mà không giữ lock trong lúc eval nặng." }]));

body.push(H2("7.3 Straggler Problem"));
body.push(P("Đã đo trong Exp 3. Kết luận: trong bounded-sync, tốc độ round = client chậm nhất (nếu chờ); WAIT_TIMEOUT cho phép cắt đuôi straggler để giữ nhịp round, đổi lại mất update của client đó trong round. Đây là lý do real-world FL thường dùng client sampling + deadline thay vì chờ tất cả.", { justify: true }));

body.push(H2("7.4 Fault Tolerance"));
body.push(P("Đã đo trong Exp 4. Kết luận: kết hợp MIN_CLIENTS=1 + WAIT_TIMEOUT + partial aggregation cho phép hệ degrade gracefully khi client crash và tự phục hồi khi client reconnect, không cần can thiệp server. Mọi transition được log để truy vết.", { justify: true }));

body.push(H2("7.5 Data Heterogeneity (Non-IID)"));
body.push(P("Đã đo trong Exp 2. Kết luận: dữ liệu lệch phân phối giữa các node làm chậm hội tụ (avg_first5 thấp hơn 3%) và giảm accuracy cuối + lệch per-class. Đây là vấn đề riêng của Federated. Trong thực tế (dữ liệu người dùng tự nhiên Non-IID), đây là thách thức trung tâm — các thuật toán như FedProx, SCAFFOLD ra đời để giảm client drift.", { justify: true }));

// ---- 8. FUTURE WORK ----
body.push(new Paragraph({ children: [new PageBreak()] }));
body.push(H1("8. Future Work"));
body.push(bullet(null, [{ t: "Communication: ", bold: true }, { t: "gradient compression, quantization, weight delta." }]));
body.push(bullet(null, [{ t: "Heterogeneity: ", bold: true }, { t: "FedProx (proximal term), SCAFFOLD (control variates) giảm client drift." }]));
body.push(bullet(null, [{ t: "Synchronization: ", bold: true }, { t: "asynchronous FL, client sampling theo deadline." }]));
body.push(bullet(null, [{ t: "Bảo mật: ", bold: true }, { t: "secure aggregation, differential privacy (hiện gửi raw weights — có thể rò rỉ thông tin)." }]));
body.push(bullet(null, [{ t: "Scale: ", bold: true }, { t: "mở rộng >2 client, đo scaling của communication + aggregation." }]));

// ---- 9. KẾT LUẬN ----
body.push(H1("9. Kết luận"));
body.push(P("Hệ thống đã hiện thực hoá đầy đủ một Federated Learning mini system 2-node với gRPC + FedAvg, và chứng minh bằng thực nghiệm cả 5 vấn đề distributed systems trọng tâm:", { justify: true }));
body.push(new Paragraph({ numbering: { reference: "numbers", level: 0 }, spacing: { after: 80 },
  children: [new TextRun({ text: "Communication overhead", bold: true }), new TextRun(" tuyến tính (6,44 MiB/round); round time bị chi phối bởi client compute + truyền mô hình chứ không phải aggregation.")] }));
body.push(new Paragraph({ numbering: { reference: "numbers", level: 0 }, spacing: { after: 80 },
  children: [new TextRun({ text: "Synchronization", bold: true }), new TextRun(" bounded-sync với tradeoff điều chỉnh được qua WAIT_TIMEOUT.")] }));
body.push(new Paragraph({ numbering: { reference: "numbers", level: 0 }, spacing: { after: 80 },
  children: [new TextRun({ text: "Straggler", bold: true }), new TextRun(": chờ (round chậm, acc cao) vs drop (round nhanh, acc giảm) — đo trực tiếp ở Exp 3.")] }));
body.push(new Paragraph({ numbering: { reference: "numbers", level: 0 }, spacing: { after: 80 },
  children: [new TextRun({ text: "Fault tolerance", bold: true }), new TextRun(": crash/recovery không làm sập hệ hay hỏng mô hình — đo ở Exp 4.")] }));
body.push(new Paragraph({ numbering: { reference: "numbers", level: 0 }, spacing: { after: 120 },
  children: [new TextRun({ text: "Data heterogeneity", bold: true }), new TextRun(": Non-IID làm chậm hội tụ + lệch per-class — đo ở Exp 2.")] }));
body.push(P("Với dữ liệu IID, Federated đạt accuracy ngang centralized (99,38% vs 99,29%) — cho thấy chi phí của phân tán nằm ở communication + đồng bộ + xử lý lỗi, đúng trọng tâm môn học, chứ không phải ở chất lượng mô hình.", { justify: true }));

// ============================================================
// DOCUMENT
// ============================================================
const doc = new Document({
  creator: "Kiencan",
  title: "Báo cáo cuối kỳ — Federated Learning Mini System",
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "Arial", color: "1F4E79" },
        paragraph: { spacing: { before: 280, after: 160 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, font: "Arial", color: "2E5C8A" },
        paragraph: { spacing: { before: 200, after: 120 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 23, bold: true, font: "Arial", color: "333333" },
        paragraph: { spacing: { before: 160, after: 100 }, outlineLevel: 2 } },
    ],
  },
  numbering: {
    config: [
      { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•",
        alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] },
      { reference: "numbers", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.",
        alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] },
    ],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
      },
    },
    footers: {
      default: new Footer({ children: [new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [
          new TextRun({ text: "Báo cáo cuối kỳ — Federated Learning Mini System   |   Trang ", size: 18, color: "888888" }),
          new TextRun({ children: [PageNumber.CURRENT], size: 18, color: "888888" }),
        ],
      })] }),
    },
    children: body,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  const out = path.join(__dirname, "Report", "bao_cao_cuoi_ky.docx");
  fs.writeFileSync(out, buf);
  console.log("WROTE " + out + " (" + buf.length + " bytes)");
});
