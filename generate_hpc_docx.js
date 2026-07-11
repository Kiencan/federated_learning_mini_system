// Sinh báo cáo cuối kỳ DOCX — HPC for AI (huấn luyện AI phân tán 2-node)
// Chạy: node generate_hpc_docx.js  →  Report/bao_cao_hpc.docx
// Cần: npm install -g docx  (dùng NODE_PATH=$(npm root -g) khi chạy)
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
    spacing: { after: 210, line: 360 },
    alignment: opts.justify === false ? undefined : AlignmentType.JUSTIFIED,
    children: [new TextRun({ text, bold: opts.bold, italics: opts.italics })],
  });
}

// Paragraph nhiều run (bold/italic inline) — runs = [{t, bold, italics}]
function PR(runs, opts = {}) {
  return new Paragraph({
    spacing: { after: 210, line: 360 },
    alignment: opts.justify === false ? undefined : AlignmentType.JUSTIFIED,
    children: runs.map((r) => new TextRun({ text: r.t, bold: r.bold, italics: r.italics })),
  });
}

function bullet(runs) {
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { after: 110, line: 360 },
    alignment: AlignmentType.JUSTIFIED,
    children: typeof runs === "string"
      ? [new TextRun(runs)]
      : runs.map((r) => new TextRun({ text: r.t, bold: r.bold, italics: r.italics })),
  });
}

function numItem(runs) {
  return new Paragraph({
    numbering: { reference: "numlist", level: 0 },
    spacing: { after: 110, line: 360 },
    alignment: AlignmentType.JUSTIFIED,
    children: typeof runs === "string"
      ? [new TextRun(runs)]
      : runs.map((r) => new TextRun({ text: r.t, bold: r.bold, italics: r.italics })),
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
      spacing: { after: 0, line: 250 },
      children: [new TextRun({ text: String(text), bold: head || bold, color: head ? "FFFFFF" : "000000", size: 20 })],
    })],
  });
}

function table(widths, rows, { headRow = true } = {}) {
  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: widths,
    rows: rows.map((r, ri) =>
      new TableRow({
        tableHeader: headRow && ri === 0,
        children: r.map((c, ci) =>
          cell(c, widths[ci], {
            head: headRow && ri === 0,
            align: ci === 0 ? AlignmentType.LEFT : AlignmentType.CENTER,
          })),
      })),
  });
}

// Callout box: single-cell shaded table cho "điểm chính / nhận xét"
function callout(title, runsList, fill = "EAF1F8") {
  const kids = [];
  if (title) kids.push(new Paragraph({ spacing: { after: 60 },
    children: [new TextRun({ text: title, bold: true, size: 20, color: "1F4E79" })] }));
  runsList.forEach((runs) => kids.push(new Paragraph({
    spacing: { after: 40, line: 264 }, alignment: AlignmentType.JUSTIFIED,
    children: typeof runs === "string" ? [new TextRun({ text: runs, size: 20 })]
      : runs.map((r) => new TextRun({ text: r.t, bold: r.bold, italics: r.italics, size: 20 })),
  })));
  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: [CONTENT_W],
    rows: [new TableRow({ children: [new TableCell({
      borders: { top: { style: BorderStyle.SINGLE, size: 4, color: "1F4E79" },
        bottom: { style: BorderStyle.SINGLE, size: 4, color: "1F4E79" },
        left: { style: BorderStyle.SINGLE, size: 12, color: "1F4E79" },
        right: { style: BorderStyle.SINGLE, size: 4, color: "1F4E79" } },
      shading: { fill, type: ShadingType.CLEAR },
      margins: { top: 100, bottom: 100, left: 160, right: 160 },
      children: kids,
    })] })],
  });
}

function figure(file, ratio, caption, wPx = 600) {
  const hPx = Math.round(wPx / ratio);
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { before: 140, after: 60 },
      children: [new ImageRun({
        type: "png", data: fs.readFileSync(file),
        transformation: { width: wPx, height: hPx },
        altText: { title: caption, description: caption, name: caption },
      })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { after: 200 },
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
  new Paragraph({ spacing: { before: 2200, after: 200 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: "BÁO CÁO CUỐI KỲ", bold: true, size: 56, color: "1F4E79" })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 },
    children: [new TextRun({ text: "HPC for AI — High-Performance Computing for AI", size: 26, color: "555555" })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 560, after: 160 },
    children: [new TextRun({ text: "HUẤN LUYỆN AI PHÂN TÁN TRÊN HỆ 2-NODE", bold: true, size: 38 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 },
    children: [new TextRun({ text: "Khi nào phân tán tăng tốc? Nút cổ chai ở đâu?", size: 26, italics: true, color: "2E5C8A" })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 240, after: 80 },
    children: [new TextRun({ text: "Federated Learning 2-node · gRPC + FedAvg · CIFAR-10", size: 22, color: "555555" })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 },
    children: [new TextRun({ text: "Hai chế độ compute: CifarCNN (nhẹ) · ResNet-18 (nặng)", size: 22, color: "555555" })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 1500, after: 80 },
    children: [new TextRun({ text: "Trọng tâm phân tích — hiệu năng song song", size: 24, bold: true })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 },
    children: [new TextRun({ text: "Speedup · Efficiency · Strong scaling · Định luật Amdahl · Định vị bottleneck", size: 20, color: "555555" })] }),
  new Paragraph({ children: [new PageBreak()] }),
);

// ---- MỤC LỤC ----
body.push(
  H1("Mục lục"),
  new TableOfContents("Mục lục", { hyperlink: true, headingStyleRange: "1-3" }),
  new Paragraph({ children: [new PageBreak()] }),
);

// ============================================================
// CHƯƠNG 1 — GIỚI THIỆU
// ============================================================
body.push(H1("1. Giới thiệu"));
body.push(P("Chương này đặt bối cảnh cho toàn bộ báo cáo: vì sao huấn luyện AI hiện đại buộc phải phân tán qua nhiều thiết bị, vì sao việc phân tán lại là một bài toán của High-Performance Computing (HPC) chứ không đơn thuần là kỹ thuật, và những câu hỏi cụ thể mà báo cáo sẽ trả lời bằng thực nghiệm. Chúng tôi cũng nêu trước các kết quả cốt lõi và đóng góp chính, để người đọc có bản đồ tổng thể trước khi đi vào chi tiết ở các chương sau."));

body.push(H2("1.1  Bối cảnh: huấn luyện AI phân tán & nhu cầu HPC"));
body.push(P("Trong một thập kỷ qua, nhu cầu tính toán để huấn luyện các mô hình học sâu (deep learning) đã tăng theo cấp số nhân — nhanh hơn nhiều so với tốc độ cải thiện của một bộ xử lý đồ hoạ (GPU) đơn lẻ. Các mô hình thị giác máy tính hiện đại có hàng chục tới hàng trăm triệu tham số; các mô hình ngôn ngữ lớn có hàng tỷ tới hàng nghìn tỷ tham số. Song song với sự phình to của mô hình là sự bùng nổ của dữ liệu huấn luyện. Hệ quả tất yếu: khi mô hình và dữ liệu vượt qua giới hạn bộ nhớ và thông lượng của một thiết bị, việc phân tán tính toán qua nhiều node trở thành yêu cầu bắt buộc, không còn là lựa chọn."));
body.push(P("Chính tại điểm này, huấn luyện học sâu giao thoa với High-Performance Computing. HPC là ngành nghiên cứu cách khai thác nhiều đơn vị tính toán song song một cách hiệu quả, và bộ công cụ khái niệm của nó — speedup (độ tăng tốc), efficiency (hiệu suất song song), strong/weak scaling, và định luật Amdahl — chính là ngôn ngữ đúng để nói về huấn luyện phân tán. Một hệ huấn luyện nhiều GPU về bản chất là một chương trình song song: nó chỉ đáng giá nếu phần công việc được chia nhỏ và chạy đồng thời đủ lớn để bù lại các chi phí phát sinh khi phối hợp nhiều node."));
body.push(P("Có hai trục song song hoá chính trong huấn luyện học sâu. Thứ nhất là data parallelism (song song theo dữ liệu): mỗi worker giữ một bản sao đầy đủ của mô hình nhưng xử lý một phần khác nhau của dữ liệu, rồi định kỳ đồng bộ các cập nhật tham số. Thứ hai là model parallelism (song song theo mô hình): bản thân mô hình được xẻ ra và trải trên nhiều thiết bị, cần thiết khi mô hình quá lớn để vừa một GPU. Báo cáo này tập trung vào data parallelism — hình thức phổ biến nhất và cũng là nền tảng của Federated Learning."));
body.push(PR([
  { t: "Điều quan trọng — và thường bị bỏ qua — là phân tán không \"miễn phí\". ", bold: true },
  { t: "So với huấn luyện trên một máy, một hệ phân tán phải trả thêm hai loại chi phí hoàn toàn không tồn tại ở chế độ đơn máy: " },
  { t: "(1) chi phí truyền thông (communication)", bold: true },
  { t: " — các node phải trao đổi tham số mô hình qua mạng ở mỗi vòng đồng bộ; và " },
  { t: "(2) chi phí đồng bộ hoá (synchronization)", bold: true },
  { t: " — các node phải chờ nhau để cùng nhịp, và tốc độ tổng thể thường bị ghìm bởi node chậm nhất (straggler)." },
]));
body.push(P("Hai chi phí này đặt ra một câu hỏi tưởng chừng ngược đời: liệu thêm một máy thứ hai có luôn làm huấn luyện nhanh hơn không? Trực giác kỹ thuật thường trả lời \"có\" — nhiều tài nguyên hơn thì nhanh hơn. Nhưng định luật Amdahl cảnh báo điều ngược lại có thể xảy ra: nếu phần công việc song song hoá được quá nhỏ so với phần tuần tự (bao gồm điều phối, mạng, đồng bộ), thì việc thêm node không những không tăng tốc mà còn có thể làm chậm đi vì phải gánh thêm overhead. Đây chính là hiện tượng mà báo cáo sẽ chứng minh bằng số liệu đo thật."));
body.push(P("Federated Learning (FL) là một hiện thân đặc biệt của data parallelism, và là bàn thử nghiệm được chọn cho báo cáo này. Trong FL, dữ liệu không được gom về một trung tâm; mỗi client giữ phần dữ liệu (shard) riêng và chỉ gửi tham số mô hình đã huấn luyện cục bộ về một server để tổng hợp. Kiến trúc này ra đời vì lý do bảo vệ quyền riêng tư, nhưng đối với báo cáo, điều hấp dẫn là FL bộc lộ đầy đủ mọi đặc trưng của một hệ phân tán thực: truyền thông qua mạng vật lý, đồng bộ theo vòng (round), straggler, và mất cân bằng tải. Nó là một môi trường thu nhỏ nhưng trung thực để đo đạc các hiện tượng HPC."));
body.push(...figure(FIG("cifar_scaling_speedup.png"), 8 / 5,
  "Hình 1.1 — Cùng một hệ 2-node, với mô hình nhẹ (CifarCNN) phân tán CHẬM hơn 1 máy (0,78×), nhưng với mô hình nặng (ResNet-18) phân tán THẮNG 1,96×. Chiều của kết quả do cường độ compute quyết định."));
body.push(PR([
  { t: "Để cụ thể hoá ngay từ đầu: ", },
  { t: "trong thí nghiệm của chúng tôi, với mô hình nhẹ (CifarCNN, ~620K tham số), hệ 2 máy chạy CHẬM hơn 1 máy — 14,48 giây mỗi vòng so với 11,34 giây (phân tán thua 1,28×). ", bold: true },
  { t: "Nhưng khi thay bằng mô hình nặng (ResNet-18, ~11,2 triệu tham số) đủ để làm bão hoà GPU, hệ 2 máy lại NHANH hơn 1 máy 1,96 lần với hiệu suất song song 98%. ", bold: true },
  { t: "Cùng một phần cứng, cùng một hệ thống — chỉ đổi độ nặng của mô hình — mà chiều của kết luận đảo ngược hoàn toàn. Chính nghịch lý này là động lực và trục xuyên suốt của báo cáo." },
]));

body.push(H2("1.2  Câu hỏi nghiên cứu: khi nào phân tán tăng tốc? Nút cổ chai ở đâu?"));
body.push(P("Từ bối cảnh trên, báo cáo tập trung trả lời ba câu hỏi nghiên cứu có quan hệ chặt chẽ với nhau. Mỗi câu hỏi được đặt ra như một giả thuyết cần kiểm chứng bằng đo đạc, không phải bằng suy luận trực giác."));
body.push(H3("Câu hỏi 1 — Khi nào phân tán thực sự tăng tốc?"));
body.push(P("Với cùng một hệ 2-node và cùng phần cứng, việc thêm GPU thứ hai có luôn rút ngắn thời gian huấn luyện không? Thực nghiệm cho thấy câu trả lời phụ thuộc quyết định vào cường độ tính toán của mỗi vòng. Chúng tôi đặt giả thuyết: phân tán chỉ tăng tốc khi khối lượng compute đủ lớn để một GPU đơn bị bão hoà; khi đó hai client dùng chung một GPU buộc phải chạy nối tiếp (serialize), và việc tách chúng ra hai GPU riêng mới giải phóng được song song thật. Ngược lại, khi compute quá nhẹ, GPU chưa bão hoà, hai client chia sẻ một GPU gần như miễn phí, nên việc phân tán chỉ tổ làm phát sinh thêm chi phí mạng và đồng bộ."));
body.push(H3("Câu hỏi 2 — Nút cổ chai nằm ở đâu?"));
body.push(P("Trực giác phổ biến khi nói về nhược điểm của Federated Learning là \"truyền mô hình qua mạng chậm\" — tức giả định hệ bị giới hạn bởi communication (communication-bound). Báo cáo kiểm chứng trực tiếp giả định này bằng cách đo phân rã từng thành phần thời gian của mỗi vòng. Nếu communication thực sự là nút cổ chai, nó phải chiếm một tỷ trọng đáng kể thời gian vòng; nếu không, ta phải đi tìm bottleneck thật ở chỗ khác (tính toán, tranh chấp tài nguyên, hay đồng bộ). Việc định vị đúng nút cổ chai là điều kiện tiên quyết để tối ưu đúng chỗ — một nguyên tắc cốt lõi của HPC."));
body.push(H3("Câu hỏi 3 — Làm thế nào để phân tán thắng?"));
body.push(P("Giả sử ta đã xác định được điều kiện và bottleneck, thì cần những can thiệp hệ thống nào để biến phân tán từ \"thua\" hoặc \"hoà\" thành \"thắng\"? Báo cáo trình bày một chuỗi tối ưu — rào đồng bộ khởi động (rendezvous barrier), chồng lấp tính toán với truyền thông (overlap), giảm độ trễ thăm dò (polling), và cân bằng tải (load balancing) — rồi đo tác động định lượng của từng bước lên chi phí điều phối. Mục tiêu là chỉ ra rằng chi phí phân tán không phải bất biến mà có thể bị thu hẹp gần như triệt tiêu bằng thiết kế đúng, và rằng khi đã kiểm soát được chi phí đó thì lợi ích của compute song song mới lộ ra trọn vẹn."));
body.push(callout("Giả thuyết trung tâm", [
  [{ t: "Lợi ích của phân tán tỷ lệ thuận với cường độ compute. ", bold: true },
   { t: "Phân tán chỉ đáng giá khi phần tính toán song song hoá được đủ lớn để lấn át phần chi phí điều phối tuần tự (mạng + đồng bộ) — đúng như định luật Amdahl mô tả. Ba câu hỏi trên cùng hướng tới việc kiểm chứng, định lượng và khai thác giả thuyết này." }],
]));

body.push(H2("1.3  Đóng góp chính"));
body.push(P("Báo cáo có sáu đóng góp chính, mỗi đóng góp được chứng minh bằng số liệu đo thực trên hệ 2-node và có thể tái lập từ các tệp nhật ký thô (round_log.csv) kèm theo."));
body.push(numItem([
  { t: "Một hệ Federated Learning 2-node được đo đạc chi tiết. ", bold: true },
  { t: "Chúng tôi xây dựng một hệ server–client hoàn chỉnh trên gRPC + Protocol Buffers, dùng thuật toán FedAvg, với mô hình đồng bộ bounded-synchronous kết hợp rendezvous barrier. Điểm nhấn là hệ được trang bị instrumentation phân rã thời gian từng vòng — tách bạch compute, communication, aggregation và evaluation — cho phép quy trách nhiệm từng mili-giây cho đúng thành phần, thay vì chỉ đo tổng thời gian như hộp đen." },
]));
body.push(numItem([
  { t: "Chứng minh thực nghiệm rằng lợi ích phân tán tỷ lệ với cường độ compute. ", bold: true },
  { t: "Với mô hình nhẹ, phân tán thua 1,28×; với mô hình nặng (ResNet-18) làm bão hoà GPU, phân tán thắng 1,96× ở hiệu suất song song 98% — đo bằng phương pháp strong scaling trên cùng khối lượng bài toán. Cặp kết quả \"nhẹ thua / nặng thắng\" trả lời trực tiếp Câu hỏi 1." },
]));
body.push(numItem([
  { t: "Định vị đúng nút cổ chai, bác bỏ trực giác \"communication là rào cản\". ", bold: true },
  { t: "Đo đạc cho thấy truyền thông chỉ chiếm khoảng 0,3% (mô hình nhẹ) đến ~2% (mô hình nặng) thời gian mỗi vòng; đường truyền Ethernet 2.5GbE (throughput thô 2,36 Gbps) thừa băng thông. Nút cổ chai thật là tranh chấp GPU (đo được 2,11× khi hai client dùng chung một GPU) và độ lệch đồng bộ giữa các node." },
]));
body.push(numItem([
  { t: "Bốn tối ưu hệ thống có kiểm chứng, triệt tiêu chi phí điều phối. ", bold: true },
  { t: "Rendezvous barrier kéo vòng đầu từ 89,6s xuống 11,0s; đưa evaluation ra khỏi đường găng giấu được ~15s eval của ResNet mỗi vòng; giảm độ trễ polling; và cân bằng tải bằng shard weighting. Tổng hợp lại, chênh lệch thời gian vòng giữa hệ 2 máy và 1 máy (mô hình nhẹ) thu hẹp từ 3,14s xuống còn 0,08s." },
]));
body.push(numItem([
  { t: "Rút ra bài học HPC tổng quát và có thể chuyển giao. ", bold: true },
  { t: "Kết quả minh hoạ định luật Amdahl một cách định lượng (phần tuần tự chỉ ~2% ở chế độ nặng), củng cố nguyên tắc \"chỉ song song hoá cái đang là bottleneck\" và \"đo trước, tối ưu sau\". Những bài học này áp dụng được cho mọi hệ huấn luyện phân tán, không riêng Federated Learning." },
]));
body.push(numItem([
  { t: "Kiến trúc điều phối cũng quyết định tốc độ, không chỉ cường độ compute. ", bold: true },
  { t: "Thay parameter-server tập trung bằng all-reduce phi tập trung (local-SGD, kiểu DDP/Horovod) nhanh thêm 1,37× (1 máy) đến 1,50× (2 máy) ở accuracy tương đương, vì all-reduce tránh được chi phí polling + handshake mà kiến trúc tập trung phải gánh — và chi phí đó tăng theo số node trong parameter-server nhưng gần như phẳng trong all-reduce (Chương 8)." },
]));
body.push(spacer());
body.push(P("Phần còn lại của báo cáo được tổ chức như sau. Chương 2 trình bày cơ sở lý thuyết về data parallelism, FedAvg và các khái niệm HPC. Chương 3 mô tả thiết kế hệ thống và cơ chế đo. Chương 4 nêu thiết lập thực nghiệm (phần cứng, mạng, kịch bản). Chương 5 phân tích hiệu năng nền với mô hình nhẹ và trả lời Câu hỏi 2 về nút cổ chai. Chương 6 trình bày chuỗi tối ưu và trả lời Câu hỏi 3. Chương 7 là nghiên cứu khả năng mở rộng với mô hình nặng, trả lời Câu hỏi 1 và kiểm chứng giả thuyết trung tâm. Chương 8 mở rộng sang một trục khác của HPC — kiến trúc điều phối (all-reduce phi tập trung so với parameter-server). Chương 9 thảo luận bài học, hạn chế và hướng mở rộng; Chương 10 kết luận."));
body.push(new Paragraph({ children: [new PageBreak()] }));

// ============================================================
// CHƯƠNG 2 — CƠ SỞ LÝ THUYẾT
// ============================================================
body.push(H1("2. Cơ sở lý thuyết"));
body.push(P("Chương này thiết lập nền tảng khái niệm để diễn giải chính xác các kết quả đo ở những chương sau. Chúng tôi lần lượt trình bày hai hình thức song song hoá trong huấn luyện học sâu, thuật toán FedAvg của Federated Learning, bộ khái niệm định lượng của HPC (speedup, efficiency, scaling, định luật Amdahl), và một khung phân loại nút cổ chai. Điểm mấu chốt xuyên suốt: mọi phát biểu về \"nhanh/chậm\" của một hệ phân tán chỉ có nghĩa khi được đặt trong khung định lượng này."));

body.push(H2("2.1  Data parallelism trong huấn luyện Deep Learning"));
body.push(P("Huấn luyện một mạng nơ-ron là quá trình lặp: ở mỗi bước, mô hình tính đầu ra trên một lô (batch) dữ liệu, so với nhãn để tính hàm mất mát (loss), rồi lan truyền ngược (backpropagation) để cập nhật tham số theo hướng giảm loss. Khi dữ liệu quá lớn, ta chia công việc cho nhiều worker. Có hai chiến lược song song hoá cơ bản."));
body.push(PR([
  { t: "Data parallelism (song song theo dữ liệu). ", bold: true },
  { t: "Mỗi worker giữ một bản sao đầy đủ của mô hình, nhưng chỉ xử lý một phần khác nhau của tập dữ liệu. Sau khi tính cập nhật cục bộ, các worker đồng bộ tham số (hoặc gradient) để đạt một mô hình chung. Đây là chiến lược phổ biến nhất vì đơn giản và mở rộng tốt khi mô hình còn vừa bộ nhớ một thiết bị. Chi phí đặc trưng của nó là bước đồng bộ tham số — đúng thứ mà báo cáo tập trung đo." },
]));
body.push(PR([
  { t: "Model parallelism (song song theo mô hình). ", bold: true },
  { t: "Khi bản thân mô hình quá lớn để vừa một GPU, ta xẻ mô hình (theo lớp hoặc theo tensor) và trải trên nhiều thiết bị. Chiến lược này cần thiết cho các mô hình khổng lồ nhưng phức tạp hơn và sinh ra phụ thuộc tuần tự giữa các phần. Báo cáo không dùng model parallelism; chúng tôi nêu ra để định vị phạm vi." },
]));
body.push(P("Một trục quan trọng của data parallelism là tần suất đồng bộ. Ở một cực, đồng bộ sau MỖI batch (như distributed SGD đồng bộ) giữ các bản sao mô hình luôn nhất quán nhưng trả giá bằng lượng truyền thông khổng lồ. Ở cực kia, đồng bộ thưa (nhiều bước cục bộ giữa hai lần trao đổi) giảm truyền thông nhưng để các bản sao \"trôi\" xa nhau, cần thuật toán tổng hợp khéo để vẫn hội tụ. Federated Learning nằm về phía thưa: mỗi client chạy nhiều epoch cục bộ rồi mới đồng bộ một lần mỗi vòng — một lựa chọn cố ý để giảm chi phí truyền thông, và cũng là lý do vì sao communication chiếm tỷ trọng nhỏ trong tổng thời gian (kiểm chứng ở §5.4). Chương 8 khảo sát trực tiếp trục tần suất đồng bộ này bằng cách so sánh all-reduce mỗi round với all-reduce mỗi batch."));
body.push(P("Cũng cần phân biệt tổng hợp gradient với tổng hợp trọng số (weight). Distributed SGD thường trung bình gradient rồi mới cập nhật; FedAvg trung bình chính trọng số mô hình sau khi mỗi client đã tự cập nhật cục bộ. Cách sau cho phép mỗi client dùng bộ tối ưu (optimizer) riêng và nhiều bước cục bộ, phù hợp với ràng buộc \"không di chuyển dữ liệu\" của FL. Báo cáo dùng FedAvg (tổng hợp trọng số) ở Chương 3–7, và một biến thể phi tập trung của cùng ý tưởng (all-reduce trung bình trọng số, gọi là local-SGD) ở Chương 8."));
body.push(P("Federated Learning là một biến thể của data parallelism với hai ràng buộc bổ sung: dữ liệu của mỗi worker (client) không được di chuyển khỏi nơi nó sinh ra, và việc đồng bộ diễn ra theo vòng (round) chứ không phải sau mỗi batch. Điều này làm cho FL vừa mang bản chất song song hoá của HPC, vừa mang đặc trưng của hệ phân tán (độ trễ mạng, node không đồng nhất, lỗi từng phần) — lý do nó là bàn thử nghiệm phù hợp."));

body.push(H2("2.2  Federated Learning & thuật toán FedAvg"));
body.push(P("Trong Federated Learning, một server điều phối K client. Mỗi vòng t diễn ra theo bốn bước: (1) server phát mô hình toàn cục hiện tại w_t cho các client; (2) mỗi client k huấn luyện cục bộ E epoch trên shard dữ liệu riêng, thu được mô hình w_t^k; (3) client gửi w_t^k về server; (4) server tổng hợp thành mô hình mới w_{t+1}. Thuật toán tổng hợp trung tâm là FedAvg (Federated Averaging, McMahan và cộng sự, 2017) — lấy trung bình có trọng số theo số mẫu của mỗi client:"));
body.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 120 },
  children: [new TextRun({ text: "w", italics: true }), new TextRun({ text: "t+1", italics: true, size: 16 }),
    new TextRun({ text: "  =  Σ", }), new TextRun({ text: "k", size: 16 }),
    new TextRun({ text: "  (n" }), new TextRun({ text: "k", size: 16 }), new TextRun({ text: " / n) · w" }),
    new TextRun({ text: "t+1", italics: true, size: 16 }), new TextRun({ text: "k", size: 16 }),
    new TextRun({ text: "        (n" }), new TextRun({ text: "k", size: 16 }),
    new TextRun({ text: " = số mẫu của client k,  n = Σ n" }), new TextRun({ text: "k", size: 16 }), new TextRun({ text: ")" })] }));
body.push(P("Trọng số theo số mẫu bảo đảm client có nhiều dữ liệu hơn đóng góp nhiều hơn vào mô hình chung, và cũng làm cho việc thay đổi cách chia dữ liệu (ví dụ 45/55 thay vì 50/50 trong tối ưu cân bằng tải ở Chương 6) không làm sai lệch mô hình — một tính chất chúng tôi khai thác trực tiếp. Với dữ liệu phân phối đều (IID), FedAvg xấp xỉ rất tốt gradient descent tập trung: đây là lý do lý thuyết cho việc accuracy của bản phân tán gần như trùng bản tập trung (kiểm chứng ở §5.1)."));
body.push(P("FedAvg cần một mô hình đồng bộ để quyết định khi nào một vòng \"đủ\" client để tổng hợp. Báo cáo dùng bounded-synchronous (trình bày ở §3.2): server chờ tối đa một khoảng WAIT_TIMEOUT và tổng hợp khi đạt tối thiểu MIN_CLIENTS. Lựa chọn này đặt ra tradeoff straggler kinh điển mà ta sẽ gặp lại nhiều lần."));

body.push(H2("2.3  Khái niệm HPC: speedup, efficiency, strong/weak scaling, định luật Amdahl"));
body.push(P("Để nói về hiệu năng song song một cách định lượng, HPC cung cấp một bộ chỉ số chuẩn. Báo cáo dùng nhất quán các định nghĩa sau."));
body.push(PR([{ t: "Speedup (độ tăng tốc). ", bold: true },
  { t: "S_p = T_1 / T_p, trong đó T_1 là thời gian chạy trên 1 đơn vị tính toán và T_p là thời gian trên p đơn vị. S_p > 1 nghĩa là song song có lợi; S_p < 1 nghĩa là song song phản tác dụng (chậm hơn tuần tự) — điều thực sự xảy ra với mô hình nhẹ trong báo cáo này." }]));
body.push(PR([{ t: "Efficiency (hiệu suất song song). ", bold: true },
  { t: "E_p = S_p / p — speedup chuẩn hoá theo số đơn vị. E_p = 1 (100%) là song song lý tưởng (tuyến tính). Ở chế độ nặng, chúng tôi đo E_2 = 98%, tức gần như lý tưởng trên hai GPU." }]));
body.push(PR([{ t: "Strong scaling. ", bold: true },
  { t: "Cố định tổng khối lượng bài toán, tăng số đơn vị tính toán, và đo speedup. Đây là phép đo dùng ở §7.3: cùng một bài toán (hai client, mỗi client 25.000 mẫu ResNet-18) được xử lý bởi 1 GPU (kịch bản B2) rồi 2 GPU (kịch bản B3)." }]));
body.push(PR([{ t: "Weak scaling. ", bold: true },
  { t: "Tăng khối lượng tỷ lệ với số đơn vị (mỗi đơn vị giữ tải cố định), đo xem thời gian có giữ nguyên không. Báo cáo không đo weak scaling một cách hệ thống, nhưng bàn tới nó ở phần hạn chế và hướng mở rộng (§9.3)." }]));
body.push(P("Trung tâm của mọi phân tích là định luật Amdahl. Nếu một tỷ lệ s của công việc là tuần tự (không song song hoá được) và phần còn lại (1 − s) song song hoá hoàn hảo trên p đơn vị, thì speedup tối đa là:"));
body.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 120 },
  children: [new TextRun({ text: "S", italics: true }), new TextRun({ text: "p", italics: true, size: 16 }),
    new TextRun({ text: "  =  1 / ( s + (1 − s) / p )" })] }));
body.push(P("Hệ quả quan trọng: speedup bị chặn trên bởi 1/s dù p tiến ra vô hạn. Với hệ 2-node, phần tuần tự s chính là chi phí điều phối — mạng, đồng bộ, và phần xử lý server không song song hoá được. Nếu s lớn (chi phí điều phối nặng so với compute), speedup thấp hoặc thậm chí < 1. Nếu s nhỏ, speedup tiệm cận lý tưởng. Toàn bộ câu chuyện của báo cáo có thể tóm lại thành: mô hình nhẹ làm s lớn (điều phối lấn át) nên phân tán thua; mô hình nặng + tối ưu hệ thống làm s nhỏ (chỉ ~2%) nên phân tán thắng gần lý tưởng."));
body.push(...figure(FIG("amdahl_speedup.png"), 8 / 5,
  "Hình 2.1 — Định luật Amdahl: speedup theo số GPU cho các mức phần tuần tự s. Điểm đo thực của báo cáo (p=2, S=1,96) nằm trên đường s≈2%, gần sát đường lý tưởng."));
body.push(P("Một ví dụ tính toán cụ thể giúp thấy rõ sức nặng của phần tuần tự. Giả sử phần tuần tự s = 20% (điều phối chiếm 1/5 công việc). Khi đó trên hai đơn vị (p=2), speedup tối đa chỉ là S = 1 / (0,20 + 0,80/2) = 1 / 0,60 ≈ 1,67× — mất 1/3 lợi ích lý thuyết. Nếu tăng lên bốn đơn vị (p=4), speedup cũng chỉ đạt 1 / (0,20 + 0,80/4) = 2,5× thay vì 4×, và dù có vô hạn đơn vị cũng không vượt quá 1/0,20 = 5×. Ngược lại, khi kéo s xuống 2% (thành quả tối ưu ở Chương 6), speedup trên hai đơn vị đạt 1 / (0,02 + 0,98/2) ≈ 1,96× — gần như lý tưởng. Chính phép tính này giải thích vì sao báo cáo dành cả một chương (Chương 6) để cắt giảm s trước khi kỳ vọng phân tán có lợi."));
body.push(P("Định luật Amdahl cũng có một người anh em bổ sung là định luật Gustafson, lập luận rằng trong thực tế người ta thường tăng kích thước bài toán khi có thêm tài nguyên (weak scaling) thay vì giữ nguyên (strong scaling), nhờ đó phần song song hoá được lớn dần và speedup không bị chặn cứng như Amdahl dự báo. Báo cáo này đo strong scaling (bài toán cố định), nên khung Amdahl là phù hợp; nhưng khi bàn về hướng mở rộng (§9.3) chúng tôi sẽ quay lại góc nhìn Gustafson."));
body.push(callout("Lý thuyết ↔ đo đạc: cùng bậc độ lớn, không phải trùng khớp tuyệt đối", [
  [{ t: "Ở chế độ compute nặng, ta đo được S", }, { t: "2", italics: true }, { t: " = 1,96. Giải ngược Amdahl cho p=2: 1,96 = 1/(s + (1−s)/2) ⇒ s ≈ 2%. " },
   { t: "Lưu ý: ", bold: true },
   { t: "s ở đây là phần KHÔNG chồng lấn được giữa 2 client trong một vòng — communication + aggregation xảy ra ngoài cửa sổ compute song song (round = max(train₀, train₁) + comm + agg) — chứ KHÔNG bao gồm độ lệch straggler (client nhanh idle chờ, vốn đã nằm trong cửa sổ compute song song nên không tính vào s). Con số này cùng bậc độ lớn với communication đo trực tiếp ở chế độ nặng (~1,1s/37,8s ≈ 2–3%, §7.2) — một phép kiểm tra chéo hợp lý (không phải bằng nhau tuyệt đối, vì s còn gộp cả aggregation và overhead server còn sót lại), củng cố rằng phần tuần tự chủ yếu là communication+aggregation ở chế độ nặng, không phải bị straggler chi phối." }],
]));

body.push(H2("2.4  Phân loại nút cổ chai: compute-bound / communication-bound / synchronization"));
body.push(P("Để tối ưu đúng chỗ, trước hết phải biết hệ đang bị giới hạn bởi cái gì. Chúng tôi dùng khung phân loại ba nhóm nút cổ chai, và một mục tiêu tường minh của báo cáo là ĐO xem hệ rơi vào nhóm nào, thay vì giả định."));
body.push(bullet([{ t: "Compute-bound. ", bold: true }, { t: "Thời gian bị chi phối bởi tính toán (ở đây là huấn luyện trên GPU). Phân tán giúp ích khi và chỉ khi phần compute này có thể chạy song song thật trên nhiều thiết bị. Đây là trường hợp của mô hình nặng." }]));
body.push(bullet([{ t: "Communication-bound. ", bold: true }, { t: "Thời gian bị chi phối bởi truyền dữ liệu qua mạng. Khi hệ ở nhóm này, thêm node có thể phản tác dụng vì làm tăng lưu lượng đồng bộ. Trực giác thường gán FL vào nhóm này — nhưng §5.4 sẽ cho thấy điều đó SAI trong bối cảnh của chúng tôi." }]));
body.push(bullet([{ t: "Synchronization-bound. ", bold: true }, { t: "Thời gian bị chi phối bởi việc chờ đồng bộ: rào (barrier), độ lệch khởi động, và straggler (node chậm nhất ghìm cả vòng). Cân bằng tải và chồng lấp (overlap) là chìa khoá xử lý nhóm này — đúng những tối ưu ở Chương 6." }]));
body.push(P("Ba nhóm không loại trừ nhau: một hệ thực có thể mang đặc trưng của cả ba, và trọng số thay đổi theo cấu hình. Chẳng hạn, với mô hình nhẹ hệ nghiêng về synchronization-bound (điều phối lấn át compute nhỏ); với mô hình nặng hệ trở nên compute-bound (và khi đó phân tán mới có đất diễn). Việc phân rã thời gian từng vòng (§3.4, §5.3) chính là công cụ để định lượng trọng số này."));
body.push(P("Một khái niệm bổ trợ hữu ích là sự bão hoà GPU (GPU saturation). Một GPU chỉ đạt thông lượng đỉnh khi có đủ công việc song song để lấp đầy hàng nghìn nhân tính toán của nó. Với mô hình rất nhỏ và batch nhỏ, phần lớn nhân GPU nhàn rỗi — GPU CHƯA bão hoà — nên hai tiến trình huấn luyện có thể chen nhau chạy gần như miễn phí (hệ số tranh chấp nhỏ hơn 2×). Khi mô hình đủ lớn để một tiến trình đã lấp đầy GPU, tiến trình thứ hai buộc phải xếp hàng — hệ số tranh chấp tiến tới 2× (nối tiếp hoàn toàn). Ngưỡng bão hoà này chính là ranh giới quyết định phân tán thắng hay thua, và Chương 7 sẽ đo nó trực tiếp (hệ số 2,11× cho ResNet-18). Đây là lăng kính thực dụng: trước khi thêm GPU, hãy hỏi GPU hiện tại đã bão hoà chưa."));
body.push(new Paragraph({ children: [new PageBreak()] }));

// ============================================================
// CHƯƠNG 3 — THIẾT KẾ HỆ THỐNG
// ============================================================
body.push(H1("3. Thiết kế hệ thống"));
body.push(P("Chương này mô tả hệ Federated Learning 2-node được dùng làm bàn thử nghiệm: kiến trúc giao tiếp, mô hình đồng bộ, các mô hình học máy và dữ liệu, và — quan trọng nhất cho một báo cáo về hiệu năng — cơ chế đo (instrumentation) cho phép phân rã thời gian từng vòng. Thiết kế được tối giản có chủ đích để mọi hiện tượng đo được đều truy nguyên rõ ràng về một thành phần cụ thể."));

body.push(H2("3.1  Kiến trúc 2 node (server–client, gRPC/protobuf)"));
body.push(P("Hệ gồm một server điều phối và hai client huấn luyện. Server chịu trách nhiệm phát mô hình toàn cục, tổng hợp cập nhật (FedAvg) và đánh giá (evaluation) trên tập test; mỗi client huấn luyện cục bộ trên shard dữ liệu riêng. Giao tiếp dùng gRPC trên nền Protocol Buffers qua cổng 50051. Protocol Buffers serialize trực tiếp state_dict của mô hình thành chuỗi byte nhị phân — không qua phân tích văn bản (text parsing) như JSON — nên nhỏ gọn và nhanh; gRPC lại chạy trên HTTP/2 với multiplexing, phù hợp cho việc truyền tham số lặp đi lặp lại."));
body.push(P("Toàn hệ tương tác qua đúng ba lời gọi thủ tục từ xa (RPC), giữ giao diện tối giản và dễ suy luận:"));
body.push(table([2600, 6760], [
  ["RPC", "Chức năng"],
  ["GetGlobalModel", "Client kéo mô hình toàn cục hiện tại từ server (đo là download_ms)."],
  ["SubmitUpdate", "Client gửi cập nhật sau khi huấn luyện; server qua 4 lớp kiểm tra hợp lệ (unknown_client → state_not_training → stale_round → duplicate) trước khi nhận."],
  ["GetRoundStatus", "Client thăm dò (poll) trạng thái vòng để biết khi nào bắt đầu vòng kế."],
]));
body.push(PR([
  { t: "Bố trí vật lý (quan trọng cho phân tích straggler): ", bold: true },
  { t: "trong kịch bản 2 máy, Máy 1 (hostname " }, { t: "admin", italics: true },
  { t: ") chạy đồng thời server và client-0, còn Máy 2 (hostname " }, { t: "ADMIN", italics: true },
  { t: ") chỉ chạy client-1. Việc Máy 1 kiêm cả server khiến client-0 phải chia sẻ tài nguyên với công việc điều phối + tổng hợp + đánh giá, biến nó thành node chậm hơn một cách hệ thống — một chi tiết sẽ giải thích hiện tượng mất cân bằng tải ở §6.4. (Lưu ý bổ sung: §4.1 cho thấy hai máy còn khác phiên bản PyTorch, nên độ lệch straggler lẫn cả hai yếu tố — xem thảo luận §9.2.)" },
]));
body.push(H3("Vòng đời của một round"));
body.push(P("Để làm rõ nơi từng chi phí phát sinh, dưới đây là trình tự đầy đủ của một vòng huấn luyện, nhìn từ cả server và client:"));
body.push(numItem([{ t: "Phát mô hình. ", bold: true }, { t: "Mỗi client gọi GetGlobalModel để kéo trọng số toàn cục hiện tại; server serialize state_dict qua protobuf và gửi (đo là download_ms)." }]));
body.push(numItem([{ t: "Huấn luyện cục bộ. ", bold: true }, { t: "Client tạo optimizer mới, chạy E local epoch trên shard riêng, thu mô hình cục bộ (đo là train_ms — thành phần compute chi phối)." }]));
body.push(numItem([{ t: "Gửi cập nhật. ", bold: true }, { t: "Client gọi SubmitUpdate kèm trọng số mới và số mẫu; thời lượng lời gọi này là upload." }]));
body.push(numItem([{ t: "Kiểm tra hợp lệ. ", bold: true }, { t: "Server chạy bốn lớp kiểm tra trước khi chấp nhận (mô tả bên dưới)." }]));
body.push(numItem([{ t: "Chờ theo rào. ", bold: true }, { t: "Server chờ đủ MIN_CLIENTS hoặc tới WAIT_TIMEOUT (đây là nơi straggler ghìm vòng)." }]));
body.push(numItem([{ t: "Tổng hợp FedAvg. ", bold: true }, { t: "Server trung bình trọng số theo số mẫu (đo là aggregation_time_ms — thường vài mili-giây)." }]));
body.push(numItem([{ t: "Đánh giá (nền). ", bold: true }, { t: "Server đánh giá mô hình mới trên tập test trong luồng nền, KHÔNG chặn client (đo là eval_time_ms)." }]));
body.push(numItem([{ t: "Chuyển vòng. ", bold: true }, { t: "Server tăng số vòng; client phát hiện qua GetRoundStatus (độ trễ phụ thuộc POLL_INTERVAL) và bắt đầu vòng kế." }]));
body.push(P("Mỗi bước ánh xạ tới một trường trong round_log.csv (§3.4), nên toàn bộ trình tự này đều đo được. Nhìn vào trình tự, ba nguồn overhead của phân tán hiện ra rõ: bước 1/3 là communication, bước 5 là synchronization (chờ straggler), bước 8 là polling latency — đúng ba mục tiêu tối ưu của Chương 6."));
body.push(H3("Bốn lớp kiểm tra hợp lệ của SubmitUpdate"));
body.push(P("Để hệ đúng đắn trước các tình huống lệch nhịp, server từ chối cập nhật không hợp lệ qua bốn lớp lọc tuần tự: (1) unknown_client — client không nằm trong danh sách kỳ vọng; (2) state_not_training — server không ở pha nhận cập nhật; (3) stale_round — cập nhật thuộc vòng cũ đã đóng (xảy ra khi một client bị bỏ lại phía sau); (4) duplicate — client gửi trùng trong cùng vòng. Bốn lớp này bảo đảm FedAvg chỉ tổng hợp các cập nhật đúng vòng và đúng nguồn, tránh làm hỏng mô hình bởi dữ liệu lệch nhịp — một yêu cầu correctness điển hình của hệ phân tán mà thực nghiệm đã kích hoạt thật (ví dụ lỗi stale_round khi một client vào trễ)."));

body.push(H2("3.2  Mô hình đồng bộ: bounded-synchronous + rendezvous barrier"));
body.push(P("Hệ dùng mô hình đồng bộ bounded-synchronous, nằm giữa hai thái cực. Khác synchronous thuần (chờ vô hạn mọi client — dễ bị treo bởi một client hỏng), server đặt một hạn chờ WAIT_TIMEOUT cho mỗi vòng. Khác asynchronous hoàn toàn (tổng hợp ngay khi có bất kỳ cập nhật nào — khó hội tụ), server vẫn chờ đủ tối thiểu MIN_CLIENTS trước khi tổng hợp. Hai tham số này cho phép điều chỉnh tradeoff giữa tốc độ vòng và độ đầy đủ dữ liệu."));
body.push(PR([
  { t: "Rendezvous barrier. ", bold: true },
  { t: "Một đóng góp thiết kế quan trọng là rào đồng bộ khởi động: server KHÔNG bắt đầu bấm giờ vòng 1 cho tới khi đủ cả hai client đã đăng ký (thực hiện lời gọi GetGlobalModel đầu tiên). Nếu thiếu rào này, một client khởi động chậm (phải nạp Python, torch, khởi tạo CUDA, tải dữ liệu — có thể mất cả phút) sẽ khiến vòng 1 gánh toàn bộ độ lệch khởi động giữa hai máy, làm sai lệch nghiêm trọng phép đo. Rendezvous được chặn bởi startup_timeout để không treo vĩnh viễn nếu một client không lên. Tác động định lượng của rào này (vòng đầu 89,6s → 11,0s) được trình bày ở §6.1." },
]));
body.push(P("Về cài đặt, việc tổng hợp chạy trong một luồng nền (background aggregation thread) theo thiết kế ba pha: chụp ảnh (snapshot) trạng thái dưới khoá, thực hiện phần việc nặng (tổng hợp + đánh giá) KHÔNG giữ khoá, rồi commit kết quả dưới khoá có bảo vệ. Nhờ vậy server không giữ khoá trong lúc đánh giá nặng, và quan trọng hơn, việc đánh giá có thể chồng lấp với huấn luyện của vòng kế (chi tiết ở §6.2)."));

body.push(H2("3.3  Mô hình & dữ liệu (CifarCNN nhẹ, ResNet-18 nặng, CIFAR-10)"));
body.push(P("Để kiểm chứng giả thuyết \"lợi ích phân tán tỷ lệ với cường độ compute\", báo cáo dùng hai mô hình có độ nặng chênh nhau khoảng 18 lần, chạy trên cùng một dataset. Số tham số được đếm trực tiếp từ mô hình khởi tạo trong mã nguồn."));
body.push(table([2400, 3480, 3480], [
  ["", "CifarCNN (nhẹ)", "ResNet-18 (nặng)"],
  ["Kiến trúc", "3 khối conv (32/64/128) + 2 lớp FC", "ResNet-18: conv 64 + 4 stage residual + FC 512"],
  ["Tham số (đếm thật)", "620.810 (~620K)", "11.173.962 (~11,2 triệu)"],
  ["Payload state_dict", "2,38 MiB (2.492.491 B)", "42,7 MiB (44.774.014 B)"],
  ["Vai trò", "baseline — GPU KHÔNG bão hoà", "scale-up — làm BÃO HOÀ GPU"],
]));
body.push(P("Dataset là CIFAR-10 — 50.000 ảnh huấn luyện, 10.000 ảnh test, ảnh màu 3×32×32, 10 lớp. Dữ liệu được phân hoạch IID: mỗi client giữ 25.000 mẫu với phân phối lớp đều. Các siêu tham số được giữ cố định để bảo đảm so sánh công bằng và tái lập; riêng khối lượng compute mỗi vòng được thay đổi CÓ CHỦ ĐÍCH theo chế độ."));
body.push(table([4680, 2340, 2340], [
  ["Siêu tham số cố định", "Chế độ nhẹ", "Chế độ nặng"],
  ["batch_size = 32 · lr = 0,01 · SGD(momentum=0,9) · seed = 42", "local_epochs = 2", "local_epochs = 1"],
  ["Số vòng huấn luyện (num_rounds)", "30", "3–10"],
]));
body.push(P("Chi tiết đáng chú ý: dù chế độ nặng chỉ dùng 1 local epoch (so với 2 ở chế độ nhẹ), một vòng ResNet vẫn nặng gấp khoảng bốn lần — một epoch ResNet ~34 giây so với hai epoch CifarCNN ~8 giây. Chênh lệch cường độ compute giữa hai mô hình vì thế còn lớn hơn tỷ lệ tham số, càng làm rõ ngưỡng bão hoà GPU."));

body.push(H2("3.4  Instrumentation: đo phân rã thời gian mỗi round"));
body.push(P("Vì báo cáo là về hiệu năng, chất lượng của kết luận phụ thuộc trực tiếp vào chất lượng phép đo. Mỗi vòng, hệ ghi một dòng vào round_log.csv với các trường cho phép tách bạch từng thành phần thời gian:"));
body.push(bullet([{ t: "round_wallclock_sec", bold: true }, { t: " — tổng thời gian thực của vòng (thước đo chính cho speedup)." }]));
body.push(bullet([{ t: "client_*_download_ms", bold: true }, { t: " — thời gian truyền mô hình server→client (thành phần communication phía tải xuống)." }]));
body.push(bullet([{ t: "client_*_train_ms", bold: true }, { t: " — thời gian huấn luyện cục bộ trên GPU (thành phần compute)." }]));
body.push(bullet([{ t: "aggregation_time_ms, eval_time_ms", bold: true }, { t: " — thời gian tổng hợp FedAvg và đánh giá trên tập test (thành phần server-side)." }]));
body.push(bullet([{ t: "accuracy, model_bytes", bold: true }, { t: " — độ chính xác trên test và kích thước payload, để phân tích chất lượng và chi phí truyền." }]));
body.push(PR([
  { t: "Lưu ý đo lường quan trọng: ", bold: true },
  { t: "thời gian upload (client→server) chỉ đo được ở phía client (in ra stdout), vì nó chính là thời lượng của lời gọi SubmitUpdate — server không quan sát trực tiếp được. Ngoài ra, mọi thời lượng đều đo bằng " },
  { t: "time.perf_counter", italics: true },
  { t: " (đồng hồ đơn điệu, monotonic), nên độc lập với đồng hồ tường (wall-clock) của hệ điều hành — kể cả khi đồng hồ hệ thống của một máy bị lệch ngày, các phép đo thời lượng vẫn chính xác." },
]));
body.push(P("Cách phân rã này là công cụ trung tâm của toàn báo cáo: nó cho phép, ở mỗi cấu hình, trả lời câu hỏi \"thời gian đi đâu?\" một cách định lượng — nền tảng để định vị bottleneck (§5.3–5.4), đo tác động từng tối ưu (Chương 6) và tính speedup (Chương 7)."));
body.push(new Paragraph({ children: [new PageBreak()] }));

// ============================================================
// CHƯƠNG 4 — THIẾT LẬP THỰC NGHIỆM
// ============================================================
body.push(H1("4. Thiết lập thực nghiệm"));
body.push(P("Chương này mô tả môi trường đo: phần cứng và phần mềm hai máy, đường mạng vật lý nối chúng, và ba kịch bản thí nghiệm dùng xuyên suốt báo cáo. Mục tiêu là bảo đảm mọi so sánh 1 máy vs 2 máy đều công bằng — chênh lệch quan sát được đến từ cách bố trí tính toán, không phải từ khác biệt phần cứng — và nêu thẳng những chỗ chưa hoàn toàn kiểm soát được."));

body.push(H2("4.1  Phần cứng & phần mềm: 2× NVIDIA RTX 2000 Ada"));
body.push(P("Hai máy dùng GPU giống hệt: NVIDIA RTX 2000 Ada Generation, chạy Windows. Tuy nhiên, theo run_meta.json ghi lại tại thời điểm chạy, hai máy có software stack khác nhau:"));
body.push(table([3600, 2880, 2880], [
  ["", "PyTorch", "CUDA"],
  ["Máy 1 (server + client-0)", "2.5.1+cu121", "12.1"],
  ["Máy 2 (client-1)", "2.6.0+cu124", "12.4"],
]));
body.push(PR([
  { t: "GPU đồng nhất bảo đảm so sánh 1-máy vs 2-máy công bằng ở tầng phần cứng. ", bold: true },
  { t: "Lưu ý confound (xem thêm §9.2): Máy 1 chạy PyTorch cũ hơn (2.5.1 so với 2.6.0), nên một phần độ lệch \"Máy 1 chậm hơn\" (straggler) quan sát được ở §5.3/§6.4/§7.3 có thể đến từ CẢ phiên bản phần mềm LẪN việc Máy 1 kiêm chạy server — hai biến này chưa được tách bạch trong thí nghiệm hiện tại. Điều này không ảnh hưởng tới kết luận chính (speedup 1,96× vẫn đo đúng strong-scaling giữa hai GPU song song), nhưng làm nhiễu phần phân tích straggler/cân bằng tải." },
]));

body.push(H2("4.2  Mạng: Ethernet trực tiếp 2.5GbE — latency (<1ms) & throughput (2,36 Gbps)"));
body.push(P("Hai máy được nối trực tiếp bằng một sợi cáp Ethernet (không qua switch trung gian), cấu hình địa chỉ IP tĩnh 10.0.0.1/24 cho Máy 1 và 10.0.0.2/24 cho Máy 2. Chúng tôi đặc trưng hoá đường mạng này bằng hai phép đo cơ bản của HPC networking: độ trễ (latency) và thông lượng (throughput)."));
body.push(bullet([{ t: "Latency. ", bold: true }, { t: "Đo bằng ping ở trạng thái ổn định cho kết quả dưới 1 ms mỗi lượt (gói đầu tiên có spike do phân giải ARP — hiện tượng bình thường). Độ trễ thấp này nghĩa là chi phí cố định mỗi lần trao đổi rất nhỏ." }]));
body.push(bullet([{ t: "Throughput thô. ", bold: true }, { t: "Đo bằng công cụ tự viết truyền 1 GB liên tục qua socket TCP thuần: đạt 281,9 MB/s = 2,36 Gbps (1024 MB trong 3,63 giây), tương đương ~94% băng thông danh nghĩa của liên kết 2.5GbE. Con số này cho thấy đường truyền khoẻ; nó là mốc để so sánh với nhu cầu truyền mô hình thực tế." }]));
body.push(PR([
  { t: "Ý nghĩa cho phân tích: ", bold: true },
  { t: "một mô hình CifarCNN 2,38 MiB, nếu truyền ở tốc độ bulk 281,9 MB/s, chỉ mất khoảng 9 ms. Như §5.4 sẽ định lượng, đây là lý do communication KHÔNG thể là nút cổ chai với model cỡ này — đường truyền thừa băng thông rất nhiều so với lượng dữ liệu cần trao đổi mỗi vòng." },
]));

body.push(H2("4.3  Các kịch bản: B1 centralized / B2 federated-1-máy / B3 federated-2-máy"));
body.push(P("Ba kịch bản được thiết kế để cô lập từng loại chi phí. So sánh cốt lõi của báo cáo là B2 (1 GPU) với B3 (2 GPU) trên cùng khối lượng bài toán — đây chính là phép đo strong scaling."));
body.push(table([1400, 5360, 2600], [
  ["Mã", "Mô tả", "Vai trò đo"],
  ["B1", "Centralized — gom toàn bộ dữ liệu, huấn luyện 1 tiến trình, không gRPC", "Baseline tốc độ train thuần"],
  ["B2", "Federated — server + 2 client cùng 1 máy (localhost)", "Overhead gRPC + tranh chấp GPU"],
  ["B3", "Federated — 2 máy qua Ethernet (client-1 ở Máy 2)", "Communication + song song thật"],
]));
body.push(P("Mỗi kịch bản được chạy ở cả hai chế độ compute. Ở chế độ nhẹ (CifarCNN, 30 vòng), cả B1/B2/B3 đều chạy để phân tích baseline (Chương 5). Ở chế độ nặng (ResNet-18), vì mục tiêu là đo scaling nên dùng ba cấu hình: solo (1 client/1 GPU — mốc đơn worker), B2 (2 client/1 GPU) và B3 (2 client/2 GPU); số vòng khác nhau do giới hạn thời gian (B3 chạy 10 vòng, B2 4 vòng, solo 2–3 vòng), nên với chế độ nặng ta chỉ so sánh round_wallclock ở trạng thái ổn định, không so sánh accuracy giữa chúng."));
body.push(callout("Vì sao ba kịch bản này đủ để trả lời câu hỏi nghiên cứu", [
  [{ t: "B1 vs B2 ", bold: true }, { t: "tách chi phí gRPC/đồng bộ (cùng 1 GPU, khác cách tổ chức). " },
   { t: "B2 vs B3 ", bold: true }, { t: "tách lợi ích song song hoá thật (cùng khối lượng, khác số GPU) — đây là strong scaling. " },
   { t: "Chạy cả hai chế độ compute ", bold: true }, { t: "cho phép quan sát ngưỡng chuyển từ \"phân tán thua\" sang \"phân tán thắng\". Chương 8 bổ sung một trục thứ tư — thay đổi kiến trúc điều phối thay vì số GPU — để tách bạch \"lợi ích của phân tán\" khỏi \"lợi ích của kiến trúc điều phối\"." }],
]));
body.push(H3("Phương pháp đo và bảo đảm tính công bằng"));
body.push(P("Vì mọi kết luận đều dựa trên so sánh thời gian, chúng tôi áp dụng bốn nguyên tắc phương pháp để phép đo trung thực và tái lập được."));
body.push(bullet([{ t: "Phân vai trò dữ liệu. ", bold: true }, { t: "Accuracy và hội tụ lấy từ các run baseline đủ số vòng; timing/wall-clock lấy từ các run steady-state (bỏ vòng 1 ramp). Không trộn hai loại — ví dụ không dùng wall-clock của một run ngắn để kết luận về hội tụ." }]));
body.push(bullet([{ t: "Đồng hồ đơn điệu. ", bold: true }, { t: "Mọi thời lượng đo bằng perf_counter (monotonic), độc lập đồng hồ tường — nên dù đồng hồ hệ thống của một máy từng lệch ngày, các con số thời lượng vẫn đúng." }]));
body.push(bullet([{ t: "Trung bình steady-state. ", bold: true }, { t: "Các con số vòng là trung bình từ vòng 2 trở đi, loại bỏ hiệu ứng khởi động/làm nóng; rendezvous (§6.1) bảo đảm ngay cả vòng 1 cũng không bị nhiễu." }]));
body.push(bullet([{ t: "Truy nguyên run. ", bold: true }, { t: "Mỗi số liệu gắn với một thư mục run cụ thể dưới Report/data (kèm run_meta.json ghi hostname, GPU, phiên bản) và có thể sinh lại hình bằng analyze_cifar.py / analyze_heavy.py / analyze_allreduce.py — bảo đảm minh bạch và kiểm chứng độc lập." }]));
body.push(P("Tính tương đương phần cứng giữa hai máy — điều kiện cho so sánh công bằng — được kiểm chứng thực nghiệm một phần: thời gian steady-state của B2 đo trên Máy 1 khớp với đo trên Máy 2, và accuracy của B1 trùng nhau do cùng seed. Yếu tố \"remote\" duy nhất trong hệ là client-1 chạy trên Máy 2 qua Ethernet ở kịch bản B3 — đúng bản chất thí nghiệm phân tán mà báo cáo muốn đo. Riêng khác biệt phiên bản phần mềm (§4.1) là hạn chế còn tồn đọng, được nêu minh bạch ở §9.2 thay vì che giấu."));
body.push(new Paragraph({ children: [new PageBreak()] }));

// ============================================================
// CHƯƠNG 5 — PHÂN TÍCH HIỆU NĂNG NỀN (BASELINE, CifarCNN nhẹ)
// ============================================================
body.push(H1("5. Phân tích hiệu năng nền (Baseline)"));
body.push(P("Chương này phân tích hiệu năng của hệ với mô hình nhẹ CifarCNN — cấu hình \"nền\" trước khi áp dụng bất kỳ tối ưu nào và trước khi scale-up compute. Bốn câu hỏi được trả lời tuần tự: phân tán có làm giảm độ chính xác không; thời gian huấn luyện 1 máy so với 2 máy ra sao; thời gian mỗi vòng đi vào đâu; và vì sao communication — trái với trực giác — không phải nút cổ chai. Mọi số liệu lấy từ các run có rendezvous (B1: exp_cifar_centralized/m1; B2: m1_rv; B3: m1_rv2)."));

body.push(H2("5.1  Độ chính xác & tính đúng đắn khi phân tán"));
body.push(P("Câu hỏi đầu tiên là tính đúng đắn: việc phân tán dữ liệu và huấn luyện qua nhiều node có làm giảm chất lượng mô hình so với huấn luyện tập trung không? Bảng dưới đối chiếu độ chính xác trên tập test của ba kịch bản."));
body.push(table([4680, 2340, 2340], [
  ["Kịch bản", "Best acc", "Final acc"],
  ["B1 Centralized", "81,17%", "80,26%"],
  ["B2 Federated 1 máy", "82,24%", "81,97%"],
  ["B3 Federated 2 máy", "82,11%", "81,73%"],
]));
body.push(P("Ba kịch bản đạt độ chính xác gần như bằng nhau, trong khoảng ~81–82%. Đáng chú ý, hai cấu hình federated còn nhỉnh hơn centralized một chút — do mỗi vòng federated có 2 local epoch, nên 30 vòng tương đương ~60 lượt quét dữ liệu so với 30 epoch của centralized. Điểm cốt lõi: với dữ liệu IID, FedAvg xấp xỉ rất tốt gradient descent tập trung, nên phân tán KHÔNG làm giảm chất lượng mô hình."));
body.push(callout("Ghi chú ngân sách compute — cân lại cho công bằng", [
  [{ t: "Con số B1 = 81,17% ở trên hơi thấp vì phép so sánh CHƯA cân compute", bold: true },
   { t: " — federated dùng local_epochs=2 nên mỗi vòng bơm gấp đôi gradient work so với 1 epoch centralized. Cân lại (centralized 60 epoch = cùng 3.000K image-pass): centralized đo 4 seed (42/1/7/123) đạt " },
   { t: "81,72 ± 0,25%", bold: true },
   { t: "; federated (seed 42) đạt best " },
   { t: "82,11%", bold: true },
   { t: " — nằm trong/trên dải centralized, chênh <0,5%. (Federated chưa chạy đa-seed; nhưng all-reduce local-SGD — cùng thuật toán model-averaging — đo 4 seed cho 82,06 ± 0,30%, §8.2, xác nhận vùng ~82%.) Kết luận parity được củng cố khi cân đúng ngân sách: phân tán KHÔNG thắng cũng KHÔNG thua centralized về chất lượng." }],
]));
body.push(...figure(FIG("cifar_accuracy_per_round.png"), 8 / 5,
  "Hình 5.1 — Đường hội tụ accuracy theo vòng của B1/B2/B3 (CifarCNN). Ba đường bám sát nhau, xác nhận phân tán không làm giảm chất lượng mô hình."));
body.push(P("Ngoài giá trị cuối, hình dạng đường hội tụ cũng đáng chú ý: cả ba kịch bản tăng nhanh trong ~10 vòng đầu rồi bão hoà quanh 81–82% — đây là giới hạn năng lực của một mô hình nhỏ như CifarCNN trên CIFAR-10, không phải giới hạn của việc phân tán. Việc B2/B3 gần như chồng khít lên nhau qua từng vòng (không chỉ ở giá trị cuối) là bằng chứng mạnh rằng thứ tự tổng hợp và ranh giới mạng không đưa thêm nhiễu vào quỹ đạo học. Nói theo ngôn ngữ hệ phân tán, đây là tính đúng đắn (correctness) của FedAvg khi triển khai phân tán: cùng đầu vào (seed, dữ liệu, siêu tham số) cho cùng hành vi, bất kể bố trí vật lý."));
body.push(PR([{ t: "Kết luận §5.1: ", bold: true },
  { t: "chi phí của phân tán KHÔNG nằm ở chất lượng mô hình mà nằm ở thời gian và chi phí điều phối — đúng trọng tâm của một báo cáo HPC. Các mục còn lại của chương tập trung định lượng chi phí đó." }]));

body.push(H2("5.2  Thời gian huấn luyện: 1 máy vs 2 máy"));
body.push(P("Nếu accuracy như nhau, thì câu hỏi hiệu năng thực sự là: hệ 2 máy có huấn luyện nhanh hơn 1 máy không? Bảng dưới so sánh thời gian mỗi vòng (với B1 là mỗi epoch)."));
body.push(table([4680, 4680], [
  ["Kịch bản", "Thời gian mỗi vòng"],
  ["B1 Centralized", "7,92 s / epoch (tổng 237,6 s cho 30 epoch)"],
  ["B2 Federated 1 máy", "11,34 s / vòng"],
  ["B3 Federated 2 máy", "14,48 s / vòng"],
]));
body.push(callout("Phát hiện phản trực giác", [
  [{ t: "Với mô hình nhẹ, hệ 2 máy (B3, 14,48 s) CHẬM HƠN hệ 1 máy (B2, 11,34 s) — phân tán THUA 1,28×. ", bold: true },
   { t: "Thêm một GPU lại làm chậm đi." }],
]));
body.push(P("Vì sao? Mô hình nhẹ (train chỉ ~8 giây) KHÔNG làm bão hoà GPU. Do đó khi hai client dùng chung một GPU (B2), chúng gần như không phải chờ nhau — GPU còn dư năng lực xử lý chồng lấn. Trong khi đó, B3 phải gánh thêm chi phí truyền thông qua mạng vật lý và, quan trọng hơn, độ lệch đồng bộ giữa hai máy — đặc biệt là straggler Máy 1 (kiêm server) chậm hơn Máy 2 (phân tích ở §6.4). Kết quả là chi phí điều phối tăng thêm lớn hơn lợi ích chia GPU (vốn gần bằng 0 vì GPU chưa bão hoà). Đây chính là minh hoạ trực tiếp của định luật Amdahl: khi phần song song hoá quá nhỏ, phần tuần tự (điều phối) lấn át và speedup rơi xuống dưới 1."));
body.push(...figure(FIG("round_wallclock_curve.png"), 8 / 4.5,
  "Hình 5.1b — Thời gian mỗi vòng của B3 (CifarCNN) theo vòng. Nhờ rendezvous, vòng 1 đã sạch (không còn spike khởi động); phần còn lại dao động quanh mức steady-state ~14,5s."));
body.push(P("Đường cong thời gian mỗi vòng bổ sung một quan sát quan trọng về phương pháp: sau khi áp dụng rendezvous barrier (§6.1), vòng 1 KHÔNG còn là ngoại lệ — nó đã về ngang các vòng sau, xác nhận rằng con số 14,48s là thời gian steady-state trung thực chứ không bị nhiễu bởi độ trễ khởi động. Nếu không có rendezvous, vòng 1 sẽ vọt lên gần 90 giây (xem §6.1) và làm sai lệch mọi trung bình. Đây là lý do vì sao chúng tôi nhấn mạnh chất lượng phép đo trước khi rút kết luận: một phép đo bị nhiễu ở vòng đầu có thể dẫn tới kết luận sai về hiệu năng tổng thể."));
body.push(P("Cần lưu ý một điểm tinh tế về cách diễn giải con số speedup < 1. Việc B3 chậm hơn B2 KHÔNG có nghĩa mạng hay phần cứng có lỗi; nó là hệ quả logic của định luật Amdahl khi phần song song hoá được (compute) quá nhỏ. Nói cách khác, phân tán \"thua\" ở đây là một kết quả ĐÚNG và dự đoán được, không phải một trục trặc kỹ thuật. Việc thừa nhận thẳng thắn kết quả này — thay vì che giấu — chính là điểm mấu chốt để đặt đúng câu hỏi tiếp theo: cần điều kiện gì để phân tán thắng (Chương 7)."));

body.push(H2("5.3  Phân rã round: compute vs communication vs synchronization"));
body.push(P("Để hiểu 14,48 giây của một vòng B3 đi vào đâu, ta phân rã theo các thành phần đo được:"));
body.push(table([2680, 1600, 1080, 4000], [
  ["Thành phần", "Thời gian", "% vòng", "Ghi chú"],
  ["Compute (client train)", "~10,4 s", "72%", "Bị chặn bởi client chậm nhất: c0/Máy 1 = 10,4s, c1/Máy 2 = 7,9s"],
  ["Evaluation (server)", "~2,9 s", "20%", "TRÊN critical path ở baseline — client chờ server eval xong mới sang vòng sau (§6.2 chuyển off-path)"],
  ["Sync/polling overhead", "~1,1 s", "8%", "Rendezvous, poll trạng thái (POLL_INTERVAL=2s — §6.3 giảm)"],
  ["Communication (down+up)", "~40 ms", "0,3%", "download 21ms + upload ~20ms"],
  ["Aggregation (server)", "~4 ms", "~0%", "Gần như vô hình"],
]));
body.push(P("Bức tranh rất rõ: thời gian một vòng bị chi phối tuyệt đối bởi compute (huấn luyện GPU), cụ thể là bởi client CHẬM NHẤT. Dù client-1 (Máy 2) train xong sau ~7,9 giây, cả vòng vẫn phải chờ client-0 (Máy 1) tới ~10,4 giây — đúng bản chất của đồng bộ theo rào: tốc độ vòng = tốc độ node chậm nhất. Đây là dấu hiệu synchronization-bound do mất cân bằng tải, và là mục tiêu của tối ưu cân bằng tải ở §6.4."));
body.push(PR([{ t: "Đáng chú ý: ", bold: true },
  { t: "ở baseline, evaluation (~2,9s) nằm TRÊN critical path — chiếm 20% thời gian vòng, client ngồi chờ trong khi server eval. Đây chính là mục tiêu của opt-A (§6.2): chuyển eval xuống chạy nền song song với vòng sau. Xác nhận bằng thứ tự sự kiện aggregation_done → evaluation_done → round_done (eval diễn ra trước khi vòng được advance ở thiết kế baseline)." }]));
body.push(...figure(FIG("cifar_round_time_breakdown.png"), 7 / 5,
  "Hình 5.2 — Phân rã thời gian mỗi vòng. Compute (train) áp đảo; eval chiếm 20% (sẽ được chuyển off-path ở §6.2); communication và aggregation gần như không nhìn thấy."));

body.push(H2("5.4  Vì sao communication (~0,3%) KHÔNG phải nút cổ chai"));
body.push(P("Đây là kết quả then chốt, bác bỏ trực tiếp trực giác phổ biến \"truyền mô hình qua mạng là nút cổ chai của Federated Learning\". Communication chỉ chiếm khoảng 0,3% thời gian mỗi vòng (40 ms trên tổng 14.480 ms)."));
body.push(PR([
  { t: "Lý do định lượng: ", bold: true },
  { t: "mô hình 2,38 MiB, đường truyền đạt 281,9 MiB/s, nên nếu chạy ở tốc độ bulk thì truyền thuần chỉ mất ~9 ms; đo thực tế download ~21 ms (phần chênh là overhead gRPC + độ trễ bắt tay, không phải giới hạn băng thông). Nói cách khác, đường truyền 2.5GbE thừa sức: nó có thể tải mô hình nhanh hơn nhiều so với nhu cầu mỗi vòng." },
]));
body.push(PR([{ t: "Băng thông không phải rào cản ", bold: true },
  { t: "— link 2.5GbE thừa sức. Trực giác \"truyền model là bottleneck của FL\" SAI trong bối cảnh này; bottleneck thật là compute (và ở B3, thêm đồng bộ). Đây là kết quả then chốt định hướng toàn bộ phần tối ưu: phải tấn công compute + sync, không phải communication." }]));
body.push(...figure(FIG("cifar_communication_overhead.png"), 6 / 5,
  "Hình 5.3 — Download mô hình mỗi vòng: localhost (B2) so với Ethernet (B3). Cả hai đều ở mức mili-giây, không đáng kể so với ~10s compute."));
body.push(PR([{ t: "Ghi chú đo lường (tail latency của upload). ", bold: true, italics: true },
  { t: "Thời gian upload qua Ethernet có phân phối lưỡng cực (bimodal): phần lớn vòng ~20 ms nhưng thỉnh thoảng bật lên ~370–430 ms, do tương tác Nagle/delayed-ACK ở tầng TCP với gói nhỏ. Đây là một hiện tượng jitter thú vị của mạng thật, nhưng không đổi kết luận: ngay cả khi tính cả các spike, communication vẫn dưới 1% thời gian vòng.", italics: true }]));
body.push(...figure(FIG("upload_bimodal.png"), 8 / 4.5,
  "Hình 5.3b — Phân phối thời gian upload mỗi vòng (client-1, Ethernet). Hai cụm rõ rệt: ~20 ms (phần lớn vòng) và ~380 ms (thỉnh thoảng) — dấu hiệu của tương tác Nagle/delayed-ACK với gói nhỏ, không phải giới hạn băng thông."));
body.push(P("Hiện tượng lưỡng cực này đáng bàn thêm vì nó minh hoạ một sự thật của mạng thực mà mô hình băng thông thuần bỏ sót. Nếu chỉ nhìn băng thông (2,36 Gbps), ta sẽ dự đoán mọi vòng truyền model 2,38 MiB trong ~9 ms. Nhưng gói dữ liệu nhỏ không đủ lớn để khấu hao độ trễ khứ hồi và các cơ chế điều khiển tắc nghẽn của TCP; kết quả là một số vòng rơi vào bẫy delayed-ACK (~40–200 ms) hoặc chờ Nagle gộp gói, đẩy upload lên ~380 ms. Bài học nhỏ nhưng tổng quát: với thông điệp nhỏ, độ trễ và overhead-mỗi-thông-điệp quan trọng hơn băng thông thô. Dù vậy, vì compute áp đảo (~10 giây/vòng), ngay cả cụm chậm 380 ms cũng chỉ là ~3% thời gian vòng, nên kết luận \"communication không phải nút cổ chai\" vẫn vững."));
body.push(new Paragraph({ children: [new PageBreak()] }));

// ============================================================
// CHƯƠNG 6 — TỐI ƯU HIỆU NĂNG
// ============================================================
body.push(H1("6. Tối ưu hiệu năng"));
body.push(P("Chương 5 đã định vị nút cổ chai: với mô hình nhẹ, hệ bị chi phối bởi compute và đồng bộ, KHÔNG phải communication. Chương này trình bày bốn tối ưu hệ thống nhắm đúng vào các nút đó, và đo tác động định lượng của từng bước. Thước đo tổng hợp là chênh lệch thời gian vòng giữa B3 (2 máy) và B2 (1 máy) — đại diện cho \"chi phí phân tán\" thuần tuý — mà ta sẽ thu hẹp từ 3,14 s về 0,08 s."));

body.push(H2("6.1  Rendezvous barrier — loại startup latency (89,6s → 11s)"));
body.push(P("Vấn đề phát hiện đầu tiên: vòng 1 của B3 ban đầu đo tới 89,6 giây — gấp khoảng sáu lần các vòng sau. Điều tra nhật ký sự kiện cho thấy đây không phải hệ chạy chậm, mà là bấm đồng hồ sai điểm: mốc bắt đầu vòng được đặt ngay khi server khởi động, TRƯỚC khi client-1 (Máy 2) kịp kết nối. Vì Máy 2 cần thời gian nạp Python, torch, khởi tạo CUDA và tải dữ liệu, server phải ngồi chờ và toàn bộ khoảng chờ đó bị tính vào vòng 1."));
body.push(P("Cách khắc phục là thêm pha rendezvous: server chờ đủ cả hai client đăng ký rồi MỚI đặt mốc bắt đầu vòng 1. Đây là một rào đồng bộ khởi động (startup barrier) chuẩn mực của hệ phân tán, được chặn bởi startup_timeout để không treo nếu một client không lên."));
body.push(table([4680, 2340, 2340], [
  ["Cấu hình", "Vòng 1", "Ý nghĩa"],
  ["B3 trước rendezvous", "89,63 s", "Cộng cả thời gian boot Máy 2"],
  ["B3 sau rendezvous", "10,96 s", "Về ngang steady-state"],
]));
body.push(P("Vòng 1 giảm khoảng 8 lần, và quan trọng hơn là loại được nhiễu khỏi phép đo steady-state. Rendezvous cũng cải thiện B2 (localhost) nhưng ở mức nhỏ hơn, vì hai client trên cùng một máy khởi động gần như đồng thời — xác nhận rằng rào này tác dụng lớn nhất khi độ lệch khởi động giữa các node lớn, đúng trường hợp chạy xuyên máy (cross-machine)."));

body.push(H2("6.2  Overlap compute–communication (eval off critical path)"));
body.push(P("Tối ưu thứ hai là chồng lấp (overlap): đưa việc đánh giá (evaluation) của server ra khỏi đường găng (critical path), để client có thể bắt đầu huấn luyện vòng kế TRONG KHI server còn đang đánh giá mô hình vừa tổng hợp."));
body.push(P("Thiết kế ban đầu (3 pha) gộp aggregate + eval trong \"heavy work\" trước khi commit/advance → eval nằm TRÊN critical path (§5.3). opt-A tách thành 4 pha: (1) chờ + snapshot → (2) tổng hợp (FedAvg) → (3) commit + advance vòng NGAY (client được giải phóng pull model vòng kế) → (4) eval + log ở pha nền, chạy song song với client đang train vòng kế. Eval dùng một bản mô hình tạm (không chạm mô hình toàn cục) nên an toàn khi vòng sau đã bắt đầu. Nhờ vậy client bắt đầu train vòng kế TRONG KHI server còn đang đánh giá vòng trước."));
body.push(PR([
  { t: "Bằng chứng định lượng mạnh nhất — model nặng. ", bold: true },
  { t: "ResNet eval tốn ~15,3s/vòng. Nếu eval nằm trên đường găng, vòng B3 nặng phải là ~36,5s (train) + 15,3s (eval) ≈ 52s. Thực đo vòng chỉ 37,8s ≈ train 36,5s + comm 1,1s — eval 15s bị giấu hoàn toàn. Overlap tiết kiệm ~27% thời gian vòng ở chế độ nặng (52s → 37,8s)." },
]));
body.push(...figure(FIG("heavy_round_breakdown.png"), 7 / 5,
  "Hình 6.1 — Overlap (ResNet-18). Cột đặc là thời gian vòng thực đo; phần gạch chéo phía trên là ~15s đánh giá lẽ ra phải cộng vào nếu nằm trên đường găng — đã được giấu nhờ chạy nền song song vòng kế."));
body.push(P("Hình 6.1 lượng hoá trực quan lợi ích overlap: nếu evaluation nằm trên đường găng, mỗi cột sẽ cao thêm phần gạch chéo (~15–16 giây). Với B3 nặng, điều đó nghĩa là 37,8 giây sẽ phình thành ~53 giây; với B2 nặng, 74,3 giây thành ~90 giây. Overlap đã \"xoá\" phần gạch chéo đó khỏi đường găng. Đáng chú ý là lợi ích tuyệt đối của overlap (~15 giây) gần như CỐ ĐỊNH bất kể chạy trên 1 hay 2 máy — vì thời gian đánh giá phụ thuộc kích thước tập test, không phụ thuộc số node. Điều này có một hệ quả tinh tế cho scaling: khi round_wallclock giảm (nhờ thêm GPU), phần eval-giấu chiếm tỷ trọng tương đối LỚN dần, nên overlap càng trở nên thiết yếu ở quy mô lớn hơn."));
body.push(P("Với mô hình nhẹ, lợi ích của overlap nhỏ hơn (eval chỉ ~1,7–2,9 s) nhưng vẫn hiện diện; nó đóng góp một phần vào cải thiện \"opt-A\" tổng hợp ở §6.5. Đây là hiện thân của nguyên lý overlap compute/communication kinh điển trong HPC: che giấu độ trễ bằng cách xếp chồng công việc không phụ thuộc nhau. Nguyên tắc thiết kế rút ra: mọi công việc không nằm trên đường phụ thuộc dữ liệu của client (đánh giá, ghi log, checkpoint) nên được đẩy ra khỏi đường găng và chạy nền."));

body.push(H2("6.3  Giảm polling latency"));
body.push(P("Client poll trạng thái vòng mỗi POLL_INTERVAL_SEC. Với giá trị cũ 2,0 giây, sau khi server sang vòng mới, client có thể phải chờ tới ~2 giây mới phát hiện và kéo mô hình — khoảng trễ này cộng thẳng vào thời gian vòng. Giảm chu kỳ xuống 0,5 giây cắt độ trễ phát hiện còn ~0,5 giây, tiết kiệm khoảng 1–1,5 giây mỗi vòng."));
body.push(PR([{ t: "Ghi chú trung thực: ", bold: true },
  { t: "đây KHÔNG phải tối ưu compute (thời gian huấn luyện không đổi, vẫn ~8–10 giây) mà là cắt độ trễ điều phối. Cùng với overlap eval (§6.2), nó tạo nên phần lớn cải thiện của bước \"opt-A\" ở §6.5. Không nên giảm chu kỳ quá thấp vì sẽ tăng tải RPC vô ích; 0,5 giây là điểm cân bằng hợp lý cho vòng cỡ chục giây." }]));

body.push(H2("6.4  Cân bằng tải bằng shard weighting (load balancing)"));
body.push(P("§5.3 đã chỉ ra vòng bị ghìm bởi client chậm nhất, và §3.1/§4.1 giải thích vì sao: Máy 1 kiêm server (và chạy PyTorch cũ hơn) nên client-0 luôn chậm hơn client-1 một cách hệ thống. Ta đo độ lệch hoàn thành giữa hai client (chênh lệch thời gian train) ở hai cấu hình chia dữ liệu, CẢ HAI đều đã áp dụng opt-A (§6.2–6.3) để cô lập đúng tác động riêng của việc cân tải."));
body.push(table([3600, 2280, 3480], [
  ["Cấu hình shard (cùng opt-A)", "Mean |skew|", "Diễn giải"],
  ["Đều 50/50", "1,86 s", "client-0 (Máy 1) là straggler cố định"],
  ["Cân 45/55", "1,21 s", "Giảm 37%, nhưng hơi quá tay (đổi dấu)"],
]));
body.push(PR([{ t: "Lưu ý so sánh táo-táo: ", bold: true, italics: true },
  { t: "cả hai dòng trên đều chạy trên nền opt-A (run m1_opt5 so với m1_optB) để cô lập đúng tác động của shard weighting. Ở baseline CHƯA opt-A, straggler còn nặng hơn — |skew| tới 2,57s trong m1_rv2 — nhưng phần chênh đó thuộc hiệu ứng của opt-A/nhiễu đo đạc, không nên gộp vào hiệu quả riêng của cân tải.", italics: true }]));
body.push(P("Ý tưởng là cấp cho Máy 1 (chậm hơn vì kiêm server) một shard NHỎ hơn để hai client về đích cùng lúc. Cho Máy 1 45% và Máy 2 55% dữ liệu giảm độ lệch ~37% (1,86s → 1,21s). Vì FedAvg lấy trọng số theo số mẫu, việc đổi tỷ lệ chia không làm sai lệch mô hình. Tuy nhiên tỷ lệ 45/55 hơi quá tay — độ lệch đổi dấu (giờ Máy 2 lại chậm hơn), gợi ý điểm tối ưu nằm quanh 48/52. Đây là minh hoạ kinh điển của load balancing trong HPC: phải cân theo NĂNG LỰC THỰC của mỗi node (đã trừ overhead), không theo số lượng danh nghĩa."));

body.push(H2("6.5  Kết quả: triệt tiêu chi phí điều phối (chênh 3,2s → 0,1s)"));
body.push(P("Gộp các tối ưu lại và đo trên thước đo tổng hợp — chênh lệch thời gian vòng giữa B3 (2 máy) và B2 (1 máy), tức chi phí phân tán thuần — cho thấy một hành trình thu hẹp rõ rệt:"));
body.push(table([4160, 1740, 1740, 1720], [
  ["Giai đoạn", "B2 vòng", "B3 vòng", "Chênh B3−B2"],
  ["Baseline (chỉ rendezvous)", "11,34 s", "14,48 s", "+3,14 s (thua 1,28×)"],
  ["+ opt-A (overlap eval + poll)", "9,73 s", "10,66 s", "+0,93 s"],
  ["+ opt-B (cân bằng shard 45/55)", "9,73 s", "9,81 s", "+0,08 s (≈ hoà)"],
]));
body.push(callout("Kết quả cốt lõi của Chương 6", [
  [{ t: "Chi phí phân tán (mô hình nhẹ) thu hẹp từ 3,14 s xuống 0,08 s — gần như triệt tiêu. ", bold: true },
   { t: "Toàn bộ cải thiện đến từ việc cắt overhead điều phối (eval trên đường găng, độ trễ poll, mất cân bằng tải); communication không hề bị đụng tới và vẫn giữ ~0,3% suốt hành trình." }],
]));
body.push(PR([
  { t: "Nhưng \"hoà\" chưa phải \"thắng\". ", bold: true },
  { t: "Với mô hình nhẹ, tối ưu tốt nhất chỉ đưa phân tán về NGANG một máy (B3 9,81 s ≈ B2 9,73 s), không vượt qua — vì GPU chưa bão hoà nên không có phần compute song song nào để giành lợi thế. Đây chính là động lực để chuyển sang mô hình nặng ở Chương 7, nơi phân tán mới thực sự tăng tốc. Ngoài ra, rendezvous (§6.1) loại độ lệch khởi động, và ở chế độ nặng overlap eval (§6.2) giấu ~15 s mỗi vòng — các tối ưu này cùng đưa hiệu suất song song ở chế độ nặng lên 98% (§7.3)." },
]));
body.push(H3("Quan sát phụ — khả năng chịu lỗi (fault tolerance)"));
body.push(P("Trong quá trình chạy thực nghiệm, một tình huống lỗi đã xảy ra tự nhiên và đáng ghi lại vì nó minh hoạ tính bền vững của thiết kế bounded-synchronous. Ở một lần chạy, client-1 (Máy 2) chết giữa vòng 17 — nó đã kéo mô hình xong nhưng treo trước khi gửi cập nhật (biểu hiện bằng lỗi kết nối bị hủy ở tầng gRPC). Server KHÔNG sập theo: cơ chế WAIT_TIMEOUT kích hoạt, server thực hiện tổng hợp một phần (partial aggregation) với client còn lại nhờ MIN_CLIENTS = 1, và tiếp tục các vòng sau. Khi client-1 được khởi động lại, nó tái gia nhập và hệ trở lại trạng thái đủ hai client."));
body.push(P("Đây là một tính chất quan trọng của hệ phân tán mà một hệ đồng bộ thuần (chờ vô hạn) sẽ không có: một node hỏng không làm treo toàn hệ. Cái giá phải trả là các vòng \"partial\" chỉ học từ một phần dữ liệu, nên nếu kéo dài sẽ ảnh hưởng chất lượng — đúng tradeoff mà tham số WAIT_TIMEOUT và MIN_CLIENTS điều chỉnh. Lần chạy đó không được dùng cho benchmark (vì nhiều vòng chỉ có một client, làm sai lệch phép đo timing), nhưng nó là bằng chứng phụ cho thấy hệ suy giảm duyên dáng (degrade gracefully) thay vì sụp đổ — một mục tiêu thiết kế cốt lõi của điện toán phân tán."));
body.push(new Paragraph({ children: [new PageBreak()] }));

// ============================================================
// CHƯƠNG 7 — NGHIÊN CỨU KHẢ NĂNG MỞ RỘNG (SCALING STUDY)
// ============================================================
body.push(H1("7. Nghiên cứu khả năng mở rộng (Scaling study)"));
body.push(P("Các chương trước cho thấy với mô hình nhẹ, phân tán tốt nhất chỉ hoà một máy. Chương này kiểm chứng giả thuyết trung tâm — lợi ích phân tán tỷ lệ với cường độ compute — bằng cách scale-up sang mô hình nặng ResNet-18 làm bão hoà GPU, rồi đo strong scaling. Đây là chương trả lời trực tiếp Câu hỏi nghiên cứu số 1."));

body.push(H2("7.1  GPU contention & compute intensity (đo 2,11×)"));
body.push(P("Cơ chế quyết định là tranh chấp GPU (GPU contention). Câu hỏi: khi hai client dùng chung một GPU, chúng chạy song song thật hay phải nối tiếp (serialize)? Ta đo bằng mô hình nặng, so sánh thời gian train mỗi client ở ba cấu hình."));
body.push(table([4680, 4680], [
  ["Cấu hình", "Train / client"],
  ["T1 — 1 client / 1 GPU (solo)", "34,1 s"],
  ["T2 — 2 client / 1 GPU (B2 nặng)", "71,9 s"],
  ["2 client / 2 GPU (B3 nặng)", "33,1 s"],
]));
body.push(PR([
  { t: "Tỷ lệ contention = T2 / T1 = 71,9 / 34,1 ≈ 2,11×", bold: true },
  { t: " (đo bằng test contention localhost chuyên biệt; cross-check với data commit exp_cifar_heavy_solo/s2 và exp_cifar_heavy_1machine/b2b cho 72,3/34,6 ≈ 2,09× — khớp trong nhiễu). Khi GPU đã bão hoà bởi một client, thêm client thứ hai trên CÙNG GPU khiến mỗi client chậm gấp đôi — chúng serialize, không song song. Cấp cho mỗi client một GPU riêng (B3) khôi phục tốc độ về ~33s (≈ solo). Đây chính là bottleneck mà mô hình nhẹ (§5.2) che giấu (vì GPU chưa bão hoà nên contention < 2×)." },
]));
body.push(...figure(FIG("cifar_gpu_contention.png"), 3 / 2,
  "Hình 7.1 — GPU contention (ResNet-18). Hai client chung 1 GPU (B2) làm mỗi client chậm 2,11×; cấp mỗi client một GPU riêng (B3) khôi phục tốc độ đầy đủ."));

body.push(H2("7.2  Scale-up model (ResNet-18): khi nào phân tán thắng"));
body.push(P("Với ResNet-18 làm bão hoà GPU, ta so sánh B2 (2 client / 1 GPU) với B3 (2 client / 2 GPU) trên cùng khối lượng bài toán — chính là phép đo strong scaling."));
body.push(table([2600, 3380, 3380], [
  ["Kịch bản", "round_wallclock (steady)", "Train mỗi client"],
  ["B2 nặng (2 client / 1 GPU)", "74,28 s", "~72 s (serialize)"],
  ["B3 nặng (2 client / 2 GPU)", "37,83 s", "c0 36,5 s / c1 29,7 s"],
]));
body.push(P("Ở chế độ nặng, mỗi GPU trong B3 chạy đúng một client ở tốc độ đầy đủ (~34–36 giây), thay vì serialize thành 72 giây như khi chung một GPU. Phân tán thắng rõ rệt — thời gian vòng giảm gần một nửa. So với dự đoán ban đầu từ hệ số contention 2,11×, kết quả thực đo (74,28 → 37,83) khớp rất tốt."));

body.push(H2("7.3  Strong scaling: speedup 1,96× & phân tích hiệu suất song song"));
body.push(P("Tính các chỉ số HPC chuẩn trên phép đo strong scaling (cùng bài toán, 1 GPU → 2 GPU):"));
body.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 60 },
  children: [new TextRun({ text: "S", italics: true, bold: true }), new TextRun({ text: "2", bold: true, size: 16 }),
    new TextRun({ text: " = T", bold: true }), new TextRun({ text: "B2", size: 16 }),
    new TextRun({ text: " / T", bold: true }), new TextRun({ text: "B3", size: 16 }),
    new TextRun({ text: " = 74,28 / 37,83 = 1,96×        ", bold: true }),
    new TextRun({ text: "E", italics: true, bold: true }), new TextRun({ text: "2", bold: true, size: 16 }),
    new TextRun({ text: " = S", bold: true }), new TextRun({ text: "2", size: 16 }),
    new TextRun({ text: " / 2 = 98%", bold: true })] }));
body.push(P("Speedup 1,96× trên hai GPU với hiệu suất song song 98% — gần như lý tưởng. Suy ngược định luật Amdahl từ con số này: giải 1,96 = 1/(s + (1−s)/2) cho s ≈ 2%. Nghĩa là chỉ khoảng 2% thời gian là tuần tự (mạng + đồng bộ + phần server không song song hoá được), phần còn lại song song hoá gần hoàn hảo — thành quả trực tiếp của các tối ưu ở Chương 6, vốn đã kéo phần tuần tự s xuống rất thấp."));
body.push(...figure(FIG("cifar_scaling_speedup.png"), 8 / 5,
  "Hình 7.2 — Khi nào phân tán thắng: mô hình nhẹ phân tán thua (0,78×), mô hình nặng phân tán thắng 1,96×. Chiều kết quả do cường độ compute quyết định."));
body.push(PR([{ t: "Lưu ý phương pháp: ", bold: true, italics: true },
  { t: "B3 nặng chạy 10 vòng (đạt accuracy 84,71%), B2 nặng chỉ 3–4 vòng, nên KHÔNG so sánh accuracy giữa hai (khác số vòng); ta chỉ so round_wallclock ở steady-state cho mục đích scaling. Straggler nhẹ vẫn còn: client-0 (Máy 1) train 36,5 s > client-1 29,7 s, đúng như phân tích ở §6.4 và §4.1 (Máy 1 kiêm server, phần mềm cũ hơn).", italics: true }]));
body.push(P("Hiệu suất 98% xứng đáng được mổ xẻ, vì nó gần lý tưởng đến mức đáng ngờ. Phần 2% thiếu hụt so với tuyến tính hoàn hảo đến từ đâu? Ba nguồn: (1) communication qua Ethernet (~1,1 giây trên tổng 37,8 — nhưng phần lớn bị chồng lấp), (2) độ lệch straggler còn lại giữa hai client (Máy 1 train 36,5s so với Máy 2 29,7s), và (3) phần server tuần tự (tổng hợp + điều phối, vài chục mili-giây). Đáng chú ý là straggler mới là thành phần lớn nhất trong ba: nếu cân bằng tải hoàn hảo (cả hai client cùng ~33 giây), hiệu suất sẽ còn cao hơn nữa. Điều này cho thấy ngay cả ở chế độ nặng, cân bằng tải (§6.4) vẫn là đòn bẩy còn dư địa."));
body.push(P("Một câu hỏi tự nhiên: liệu hiệu suất 98% có giữ được khi mở rộng quá hai node? Định luật Amdahl với s ≈ 2% dự báo speedup lý thuyết trên p node là 1/(0,02 + 0,98/p): p=4 cho ~3,77× (hiệu suất 94%), p=8 cho ~6,6× (82%). Tuy nhiên đây là chặn trên lạc quan, vì thực tế phần tuần tự s thường TĂNG theo số node (server phải tổng hợp nhiều cập nhật hơn, rào đồng bộ chờ nhiều straggler hơn, lưu lượng mạng vào server tăng tuyến tính) — đúng hiện tượng ta đã quan sát ở Chương 8 khi so sánh param-server với all-reduce (chi phí điều phối param-server tăng ~9% khi ra 2 máy, §8.3). Vì vậy chúng tôi thận trọng: kết quả 1,96× ở p=2 là bằng chứng mạnh cho hai node, nhưng ngoại suy lên nhiều node cần đo trực tiếp (§9.3)."));
body.push(P("Cuối cùng, cần nhấn mạnh tính bền vững của kết quả contention. Hệ số 2,11× không phải một con số ngẫu nhiên: nó phản ánh việc GPU đã bão hoà tới mức hai tiến trình gần như nối tiếp hoàn toàn (nếu song song lý tưởng thì tỷ lệ là 1×; nếu nối tiếp tuyệt đối thì 2×). Con số 2,11× — hơi vượt 2× — còn gợi ý một chút chi phí chuyển ngữ cảnh (context switch) giữa hai tiến trình tranh GPU, làm chúng thậm chí còn chậm hơn cả nối tiếp thuần. Đây là bằng chứng định lượng đắt giá cho luận điểm trung tâm: khi GPU bão hoà, chia sẻ nó không những vô ích mà còn phản tác dụng, và giải pháp đúng là thêm GPU (thêm node)."));

body.push(H2("7.4  Kết luận scaling: lợi ích phân tán tỷ lệ với độ nặng compute"));
body.push(P("Đặt cạnh nhau hai chế độ compute trên cùng hệ thống và cùng phần cứng:"));
body.push(table([2960, 1760, 1720, 1560, 1360], [
  ["Model", "Compute/vòng", "B2 (1 GPU)", "B3 (2 GPU)", "Kết quả"],
  ["CifarCNN nhẹ", "~8 s", "11,34 s", "14,48 s", "thua 1,28×"],
  ["ResNet-18 nặng", "~35 s", "74,28 s", "37,83 s", "thắng 1,96×"],
]));
body.push(callout("Trả lời Câu hỏi nghiên cứu số 1", [
  [{ t: "Cùng một hệ thống, cùng phần cứng — chỉ đổi độ nặng mô hình — mà chuyển từ \"phân tán thua\" sang \"phân tán thắng gần lý tưởng\". ", bold: true },
   { t: "Điều kiện để phân tán tăng tốc là: compute phải đủ nặng để làm bão hoà GPU đơn. Khi đó tranh chấp GPU (2,11×) trở thành bottleneck mà GPU thứ hai giải phóng, và phần compute song song đủ lớn để lấn át chi phí điều phối tuần tự (Amdahl)." }],
]));
body.push(new Paragraph({ children: [new PageBreak()] }));

// ============================================================
// CHƯƠNG 8 — KIẾN TRÚC ĐIỀU PHỐI: ALL-REDUCE VS PARAMETER-SERVER
// ============================================================
body.push(H1("8. Kiến trúc điều phối: All-reduce phi tập trung vs Parameter-server"));
body.push(P("Chương 5–7 dùng và tối ưu một kiến trúc cụ thể — parameter-server: một server tập trung nhận cập nhật, chạy FedAvg, rồi phát lại mô hình. Chương này đặt câu hỏi rộng hơn: bản thân LỰA CHỌN KIẾN TRÚC ĐIỀU PHỐI có ảnh hưởng tới tốc độ hay không, tách bạch khỏi cường độ compute (Chương 7) và các tối ưu điều phối (Chương 6)? Ta trả lời bằng cách cài đặt và đo trực tiếp kiến trúc thay thế phổ biến nhất trong HPC cho huấn luyện phân tán: all-reduce ngang hàng, như dùng trong PyTorch DDP hay Horovod."));

body.push(H2("8.1  Câu hỏi & hai biến thể all-reduce"));
body.push(P("All-reduce bỏ hẳn vai trò server tập trung: mỗi node tự trao đổi và trung bình tham số trực tiếp với các node khác qua một thao tác tập thể (collective operation), không có điểm trung tâm nào nhận toàn bộ lưu lượng. Về lý thuyết, cách này tránh được nút cổ chai băng thông tại server khi số node lớn, và loại bỏ toàn bộ chi phí \"vòng ngoài\" của một kiến trúc client–server (poll, handshake, hàng đợi tại server)."));
body.push(P("Chúng tôi cài đặt allreduce_train.py bằng torch.distributed (backend gloo) với hai biến thể, giữ nguyên model/data/hyperparams để so sánh tách bạch với federated:"));
body.push(bullet([{ t: "Kiểu A — Local-SGD phi tập trung. ", bold: true }, { t: "Mỗi node train local_epochs=2 trên shard, rồi all-reduce trung bình mô hình 1 lần/round. Cấu trúc giống hệt federated (30 round × 2 local epoch), chỉ thay bước server-aggregate bằng all-reduce ngang hàng — phép so sánh công bằng nhất với Chương 5–7." }]));
body.push(bullet([{ t: "Kiểu B — Data-parallel đồng bộ. ", bold: true }, { t: "All-reduce gradient MỖI mini-batch (như DistributedDataParallel chuẩn), chạy 60 epoch để cân bằng tổng FLOPs với Kiểu A." }]));
body.push(callout("Ghi chú so sánh công bằng", [
  [{ t: "Mọi con số crit-path (critical-path time) dưới đây đều LOẠI evaluation ", bold: true },
   { t: "(all-reduce thiết kế để eval nằm off-path, giống opt-A). Do đó phải so với federated OPT-A (§6, eval cũng off-path), KHÔNG so với baseline (§5, eval on-path) — nếu không sẽ lệch kép: vừa lẫn thời gian eval, vừa so với một bản chưa được tối ưu." }],
]));

body.push(H2("8.2  Kết quả: Kiểu A nhanh 1,37–1,50× ở accuracy tương đương"));
body.push(P("Cùng phần cứng, cùng ngân sách 3.000K lượt ảnh (image-pass), cùng seed 42, đo crit-path (train + đồng bộ, loại eval):"));
body.push(table([3200, 2080, 2080, 1980], [
  ["Kiến trúc", "crit-path", "s/round", "best acc"],
  ["Federated opt-A (param-server, 1 máy)", "291,0 s", "9,70 s", "~82%"],
  ["Federated opt-A (param-server, 2 máy)", "316,8 s", "10,56 s", "~82%"],
  ["All-reduce A (1 máy)", "212,9 s", "7,10 s", "81,93%"],
  ["All-reduce A (2 máy)", "210,6 s", "7,02 s", "82,25%"],
]));
body.push(PR([{ t: "Speedup Kiểu A so với federated opt-A: ", bold: true },
  { t: "1 máy 1,37× (291→213s), 2 máy 1,50× (317→211s). (So với baseline federated CHƯA opt-A thì chênh tới 1,78× trên 2 máy — nhưng đó là so với một bản chưa tối ưu, không công bằng, nên không dùng làm kết luận chính.)" }]));
body.push(P("Accuracy không đổi. All-reduce A đo đa-seed (n=4: seed 42/1/7/123) đạt 82,06 ± 0,30%. Federated param-server (chạy seed 42) đạt best 82,11% (Phụ lục A, m1_rv2) — nằm gọn trong khoảng ±0,30% của all-reduce, chênh dưới 0,1 điểm phần trăm. Federated không chạy đa-seed nên chưa kiểm định thống kê chính thức được, nhưng khác biệt nhỏ hơn nhiều so với dao động seed của all-reduce → hai kiến trúc cho cùng chất lượng model; all-reduce chỉ nhanh hơn về tốc độ, không đánh đổi accuracy."));
body.push(...figure(FIG("cifar_allreduce_speedup.png"), 1.5,
  "Hình 8.1 — All-reduce vs parameter-server: crit-path 1 máy và 2 máy (loại eval). All-reduce nhanh hơn ở cả hai cấu hình, khoảng cách nới ra khi ra 2 máy."));

body.push(H2("8.3  Vì sao nhanh hơn — cắt điều phối, KHÔNG phải giảm truyền thông"));
body.push(P("Khác biệt KHÔNG đến từ truyền thông: cả hai kiến trúc truyền cùng 2,38 MiB/round, và communication đã được chứng minh là dưới 1% thời gian round (§5.4). Khác biệt đến từ chi phí điều phối mà param-server phải gánh còn all-reduce tránh được: polling (client poll GetRoundStatus mỗi 0,5s để phát hiện round mới → độ trễ phát hiện), handshake tuần tự (upload → server chờ đủ → aggregate → advance → poll → download — một chuỗi bước nối tiếp), và một tiến trình server thứ ba tranh chấp CPU/GPU với các client. All-reduce thay toàn bộ chuỗi này bằng một thao tác tập thể — một barrier tức thì giữa các node ngang hàng."));
body.push(P("Điều này nhất quán với phát hiện ở §5.3: bottleneck của param-server là ĐỒNG BỘ (eval on-path, poll-wait), không phải communication — và all-reduce tấn công đúng vào nhóm chi phí đó, không phải vào băng thông."));
body.push(PR([{ t: "Điểm HPC cốt lõi: ", bold: true },
  { t: "chi phí điều phối của param-server TĂNG khi ra 2 máy, còn all-reduce PHẲNG." }]));
body.push(table([3120, 2080, 2080, 2080], [
  ["", "1 máy", "2 máy", "Thay đổi"],
  ["Federated opt-A crit-path", "291,0 s", "316,8 s", "+9% tệ hơn"],
  ["All-reduce A crit-path", "212,9 s", "210,6 s", "~0% (phẳng)"],
]));
body.push(P("Dù opt-A đã giảm mạnh gánh nặng cross-machine của param-server (Chương 6), nó VẪN đội thêm ~9% thời gian khi ra 2 máy — do Ethernet, Máy-1-kiêm-server, và skew đồng bộ cộng dồn; trong khi all-reduce gần như không đổi. Đây là lý do khoảng cách nới rộng từ 1,37× (1 máy) lên 1,50× (2 máy). Kết quả này minh hoạ cụ thể một nguyên lý HPC: kiến trúc tập trung (centralized) scale kém hơn về mặt điều phối khi số node tăng — đúng động cơ lịch sử khiến all-reduce trở thành lựa chọn mặc định cho huấn luyện phân tán quy mô lớn (Horovod, PyTorch DDP)."));

body.push(H2("8.4  Kiểu B chậm 7,4× — tần suất đồng bộ chi phối, không phải khối lượng"));
body.push(table([4680, 2680, 1960], [
  ["All-reduce", "crit-path (60 epoch)", "s/epoch"],
  ["Kiểu B (all-reduce mỗi batch)", "1575,8 s", "26,26 s"],
]));
body.push(P("Kiểu B đồng bộ 782 lần mỗi epoch (một lần mỗi mini-batch) thay vì 1 lần mỗi round → chậm hơn 7,4× so với Kiểu A (1575,8s so với 212,9s), dù cùng tổng khối lượng compute (cùng 3.000K lượt ảnh)."));
body.push(callout("Bài học tần suất đồng bộ", [
  [{ t: "Tần suất đồng bộ (số lần thực hiện barrier/all-reduce) chi phối chi phí điều phối, không phải khối lượng dữ liệu mỗi lần trao đổi. ", bold: true },
   { t: "Kiểu B chỉ đáng dùng trên interconnect tốc độ cao (NVLink, InfiniBand) nơi mỗi lần đồng bộ đủ rẻ để lặp lại hàng trăm lần mỗi epoch; trên Ethernet thông thường như thí nghiệm này, nó phản tác dụng nghiêm trọng." }],
]));
body.push(...figure(FIG("cifar_allreduce_landscape.png"), 1.6,
  "Hình 8.2 — Toàn cảnh thời gian các kiến trúc (cùng ngân sách ~3000K image-pass, accuracy đều ~82%): centralized, federated (baseline và opt-A), all-reduce Kiểu A, all-reduce Kiểu B."));

body.push(H2("8.5  So với Centralized B1: 2,5× nhưng phần lớn là utilization, không phải phân tán"));
body.push(P("So all-reduce với centralized 1 máy (B1, cùng ngân sách 3.000K, chỉ đo phần train):"));
body.push(table([4680, 2340, 2340], [
  ["Cấu hình", "Thời gian", "Best acc"],
  ["Centralized B1 (1 tiến trình, 1 GPU)", "540,8 s", "81,97%"],
  ["All-reduce A (1 máy, 2 tiến trình, 1 GPU chung)", "212,9 s", "82,06%"],
  ["All-reduce A (2 máy, 2 GPU riêng)", "210,6 s", "82,25%"],
]));
body.push(PR([{ t: "All-reduce 2 máy nhanh 2,57× so với B1 — nhưng có một cú twist quan trọng: ", bold: true },
  { t: "all-reduce 1 MÁY (dùng đúng CÙNG MỘT GPU với centralized) đã đạt 2,54× rồi; máy thứ hai chỉ thêm ~1% nữa. Gần như toàn bộ tốc độ đến từ throughput mỗi batch tăng lên: 5,77 ms/batch (1 tiến trình) → 2,27 ms/batch (2 tiến trình đồng thời) trên cùng một GPU. Mô hình CifarCNN nhẹ với batch 32 khiến GPU \"nằm chờ\" giữa các kernel (overhead khởi chạy của Python/CUDA); hai tiến trình xen kẽ lấp đầy khoảng trống đó → khoảng 2,5× throughput." }]));
body.push(P("Nối lại với Chương 5–7: với mô hình nhẹ, GPU thứ hai gần như vô dụng cho tốc độ (2,54× → 2,57×, chỉ thêm ~1%); \"thắng 2,5× so với centralized\" thực chất là lấp đầy một GPU đang bị dùng thiếu — đạt được ngay trên MỘT máy bằng concurrency (nhiều tiến trình cùng GPU), KHÔNG phải lợi ích của phân tán qua nhiều máy. Ngược lại, với ResNet nặng (Chương 7): một tiến trình đã bão hoà GPU, nên concurrency chỉ gây serialize (contention 2,11×) — lúc đó GPU thứ hai (máy thứ hai) mới thực sự có giá trị."));
body.push(PR([{ t: "Công bằng mà nói: ", bold: true, italics: true },
  { t: "2,5× là so với một cấu hình centralized 1-tiến-trình khá ngây thơ; một centralized được tối ưu kỹ hơn (batch lớn hơn, torch.compile, hoặc DataParallel trong một tiến trình) nhiều khả năng sẽ thu hẹp đáng kể khoảng cách utilization này. Kết luận không phải \"all-reduce luôn thắng centralized 2,5×\" mà là \"phần lớn khoảng cách đó đến từ việc GPU bị dùng thiếu, có thể vá bằng concurrency trong một máy, không nhất thiết cần phân tán\".", italics: true }]));
body.push(new Paragraph({ children: [new PageBreak()] }));

// ============================================================
// CHƯƠNG 9 — THẢO LUẬN
// ============================================================
body.push(H1("9. Thảo luận"));
body.push(P("Chương này rút ra các bài học tổng quát từ kết quả thực nghiệm, thẳng thắn nêu hạn chế của phương pháp, và phác thảo các hướng mở rộng."));

body.push(H2("9.1  Bài học HPC: Amdahl, cân bằng tải, overlap, GPU saturation"));
body.push(bullet([{ t: "Định luật Amdahl là có thật và đo được. ", bold: true }, { t: "Cùng một hệ thống, phân tán thắng hay thua tuỳ tỷ lệ giữa compute song song và chi phí điều phối tuần tự. Mô hình nhẹ làm phần tuần tự lấn át (speedup < 1); mô hình nặng + tối ưu làm phần tuần tự chỉ còn ~2% (speedup 1,96×, hiệu suất 98%)." }]));
body.push(bullet([{ t: "Đo trước, tối ưu sau — định vị bottleneck trước khi hành động. ", bold: true }, { t: "Trực giác \"communication là rào cản của FL\" sai trong bối cảnh này (comm <1% thời gian vòng). Chỉ nhờ phân rã thời gian từng vòng, ta mới định vị đúng bottleneck thật (GPU contention + đồng bộ) và nhắm tối ưu vào đó. Tối ưu sai chỗ (ví dụ nén mạng) sẽ vô ích." }]));
body.push(bullet([{ t: "Cân bằng tải theo năng lực thực. ", bold: true }, { t: "Node kiêm việc phụ (server) phải nhận ít dữ liệu hơn; phải cân theo throughput đo được của mỗi node, không theo số lượng danh nghĩa." }]));
body.push(bullet([{ t: "Overlap để giấu độ trễ. ", bold: true }, { t: "Đưa việc nặng không nằm trên đường phụ thuộc (evaluation) ra luồng nền giấu được ~15 giây mỗi vòng ở chế độ nặng — hiện thân của nguyên lý overlap compute/communication kinh điển." }]));
body.push(bullet([{ t: "GPU saturation là điều kiện tiên quyết. ", bold: true }, { t: "Lợi ích của việc thêm GPU chỉ xuất hiện khi GPU hiện có đã bão hoà. Với workload chưa bão hoà, thêm thiết bị chỉ thêm overhead. Đây là lăng kính để quyết định có nên phân tán hay không." }]));
body.push(bullet([{ t: "Kiến trúc điều phối là một trục tối ưu độc lập với cường độ compute. ", bold: true }, { t: "All-reduce nhanh hơn param-server 1,37–1,50× ở CÙNG cường độ compute (mô hình nhẹ) vì tránh chi phí điều phối tập trung — và chi phí đó tăng theo số node trong kiến trúc tập trung, phẳng trong all-reduce (Chương 8)." }]));
body.push(P("Bảy bài học trên không rời rạc mà tạo thành một quy trình ra quyết định thống nhất. Trước một ý định phân tán, thứ tự đúng là: (1) đo xem GPU đơn đã bão hoà chưa — nếu chưa, phân tán nhiều khả năng phản tác dụng; (2) nếu đã bão hoà, phân rã thời gian vòng để định vị bottleneck thật; (3) cắt phần tuần tự s bằng các kỹ thuật điều phối (rendezvous, overlap, cân bằng tải) TRƯỚC khi thêm tài nguyên; (4) cân nhắc kiến trúc điều phối (tập trung hay ngang hàng) tuỳ quy mô dự kiến; (5) chỉ khi s đã nhỏ, thêm node mới cho speedup gần lý tưởng. Quy trình này đảo ngược trực giác \"cứ thêm máy là nhanh\" và thay bằng \"đo, tối ưu điều phối, chọn đúng kiến trúc, rồi mới mở rộng\"."));
body.push(P("Đặt trong bối cảnh thực tiễn, kết quả của báo cáo có ý nghĩa trấn an lẫn cảnh báo. Trấn an: các mô hình production (ResNet, Transformer, LLM) đều nặng hơn CifarCNN nhiều bậc, nên chúng nằm chắc ở vùng \"compute đủ nặng để phân tán thắng\" — phân tán là chiến lược đúng cho chúng, và các framework production (Horovod, PyTorch DDP) đã chọn all-reduce làm mặc định đúng vì lý do scale điều phối ở §8.3. Cảnh báo: với các workload nhẹ (mô hình nhỏ, prototype, fine-tuning nhẹ, inference-time), phân tán có thể làm chậm và tốn kém hơn; ở đó, gộp về một thiết bị mạnh (hoặc chạy nhiều tiến trình concurrent trên một GPU, như §8.5 cho thấy) thường tối ưu hơn. Ranh giới giữa hai vùng chính là ngưỡng bão hoà GPU mà báo cáo đã đo và đặt tên."));

body.push(H2("9.2  Hạn chế phương pháp"));
body.push(bullet([{ t: "Chỉ 2 node. ", bold: true }, { t: "Báo cáo chưa quan sát được scaling khi số node p > 2, nơi chi phí đồng bộ của kiến trúc tập trung thường tăng phi tuyến (đã thấy dấu hiệu ở mức nhỏ: +9% khi ra 2 máy, §8.3)." }]));
body.push(bullet([{ t: "Confound phần mềm (§4.1). ", bold: true }, { t: "Máy 1 chạy PyTorch 2.5.1+cu121, Máy 2 chạy 2.6.0+cu124. Độ lệch \"Máy 1 straggler\" (heavy: c0 36,5s vs c1 29,7s) do đó lẫn HAI biến — server co-located VÀ torch cũ hơn — chưa tách được. Cách khắc phục: đồng bộ version 2 máy rồi chạy lại, hoặc hoán đổi vai trò server giữa 2 máy để cô lập tác động. Không ảnh hưởng kết luận chính (speedup 1,96× vẫn đo strong-scaling giữa 2 GPU song song), nhưng làm nhiễu phân tích straggler/cân bằng tải chi tiết (§6.4, §7.3)." }]));
body.push(bullet([{ t: "Số vòng ít ở chế độ nặng. ", bold: true }, { t: "B2/B3 nặng chạy lần lượt 3–4/10 vòng do giới hạn thời gian; speedup dựa trên round_wallclock steady-state (ổn định, độ lệch nhỏ) nhưng cỡ mẫu vòng còn nhỏ." }]));
body.push(bullet([{ t: "Federated chưa chạy đa-seed. ", bold: true }, { t: "§5.1 và §8.2 dùng centralized và all-reduce đa-seed (n=4) để kiểm chứng độ ổn định accuracy, nhưng federated param-server chỉ chạy seed 42. Chênh lệch quan sát được (<0,5pp so với centralized đa-seed, <0,1pp so với all-reduce đa-seed) nhỏ hơn nhiều so với dao động seed-to-seed đo được ở hai kiến trúc kia, nên kết luận parity vẫn hợp lý — nhưng một kiểm định thống kê chính thức (ví dụ Welch t-test) cho federated cần chạy thêm 3 seed nữa mới thực hiện được." }]));
body.push(bullet([{ t: "Một loại phần cứng / hệ điều hành. ", bold: true }, { t: "Đo trên Windows với một dòng GPU; kết quả có thể khác trên cluster Linux/InfiniBand — nơi communication còn rẻ hơn nữa, điều này càng củng cố kết luận compute-bound chứ không mâu thuẫn." }]));
body.push(bullet([{ t: "Đồng hồ hệ thống. ", bold: true }, { t: "Đồng hồ tường của một máy từng bị lệch ngày ở vài run; tuy nhiên mọi thời lượng đều đo bằng perf_counter (đơn điệu) nên kết quả không bị ảnh hưởng — chỉ các nhãn thời gian tuyệt đối là không đáng tin." }]));

body.push(H2("9.3  Hướng mở rộng: async FL, mixed precision, >2 node"));
body.push(bullet([{ t: "Asynchronous FL. ", bold: true }, { t: "Bỏ rào chờ straggler để tăng thông lượng, đổi lại độ phức tạp về hội tụ — một hướng giảm phần tuần tự s trong Amdahl." }]));
body.push(bullet([{ t: "Mixed precision (AMP). ", bold: true }, { t: "Giảm thời gian compute mỗi vòng; điều này sẽ DỊCH ngưỡng \"đủ nặng để thắng\" lên cao hơn, vì compute nhanh hơn nghĩa là cần model/dữ liệu lớn hơn nữa để bão hoà GPU." }]));
body.push(bullet([{ t: "Mở rộng > 2 node và đo weak scaling. ", bold: true }, { t: "Kiểm tra xem hiệu suất song song có giữ được khi tăng số node (đặc biệt so sánh param-server vs all-reduce ở quy mô lớn hơn — dự đoán khoảng cách sẽ nới thêm nữa), và đặc trưng hoá chi phí đồng bộ theo p bằng khung Gustafson (§2.3) khi khối lượng cũng tăng theo." }]));
body.push(bullet([{ t: "Nén truyền thông. ", bold: true }, { t: "Gradient compression / quantization: dù communication chưa phải bottleneck ở 2 node, nó sẽ trở nên quan trọng khi số node lớn hoặc mô hình khổng lồ." }]));
body.push(bullet([{ t: "Tách bạch confound phần mềm. ", bold: true }, { t: "Đồng bộ phiên bản PyTorch/CUDA giữa hai máy, hoặc hoán đổi vai trò server, để cô lập chính xác tác động của việc co-locate server khỏi tác động của phiên bản phần mềm lên hiện tượng straggler." }]));
body.push(new Paragraph({ children: [new PageBreak()] }));

// ============================================================
// CHƯƠNG 10 — KẾT LUẬN
// ============================================================
body.push(H1("10. Kết luận"));
body.push(P("Báo cáo đã xây dựng một hệ Federated Learning 2-node (gRPC + FedAvg) được đo đạc chi tiết, và dùng nó trả lời câu hỏi HPC trung tâm — khi nào phân tán tăng tốc? — qua sáu phát hiện định lượng:"));
body.push(numItem([{ t: "Lợi ích phân tán tỷ lệ với cường độ compute. ", bold: true }, { t: "Mô hình nhẹ (CifarCNN): phân tán thua 1,28× vì GPU chưa bão hoà. Mô hình nặng (ResNet-18): phân tán thắng 1,96×, hiệu suất song song 98% — strong scaling gần lý tưởng." }]));
body.push(numItem([{ t: "Nút cổ chai KHÔNG phải communication. ", bold: true }, { t: "Truyền mô hình chỉ chiếm ~0,3% (nhẹ) đến ~2% (nặng) thời gian vòng; đường truyền 2.5GbE (2,36 Gbps) thừa băng thông." }]));
body.push(numItem([{ t: "Bottleneck thật là tranh chấp GPU + đồng bộ. ", bold: true }, { t: "GPU contention đo được 2,11× khi hai client dùng chung một GPU; cấp mỗi client một GPU riêng (B3) giải phóng nút này." }]));
body.push(numItem([{ t: "Chi phí điều phối triệt tiêu được bằng tối ưu hệ thống. ", bold: true }, { t: "Rendezvous (vòng đầu 89,6s→11s), overlap eval (giấu ~15s/vòng), giảm poll-wait, cân bằng tải — khép chênh vòng B3−B2 (nhẹ) từ 3,14s về 0,08s." }]));
body.push(numItem([{ t: "Định luật Amdahl được minh hoạ định lượng. ", bold: true }, { t: "Phần tuần tự (điều phối) chỉ ~2% ở chế độ nặng, nên phân tán chỉ đáng giá khi compute song song hoá đủ lớn để lấn át phần tuần tự này." }]));
body.push(numItem([{ t: "Kiến trúc điều phối cũng quyết định tốc độ, không chỉ cường độ compute. ", bold: true }, { t: "Thay parameter-server bằng all-reduce phi tập trung (local-SGD) nhanh 1,37× (1 máy) đến 1,50× (2 máy) ở accuracy tương đương (all-reduce 82,06±0,30% qua 4 seed ≈ federated seed-42 best 82,11%), nhờ cắt chi phí điều phối server (poll + handshake) — chi phí này vẫn tăng ~9% khi ra 2 máy dù đã opt-A, còn all-reduce phẳng. Ngược lại, all-reduce mỗi batch chậm 7,4×: tần suất đồng bộ chi phối, không phải khối lượng (Chương 8)." }]));
body.push(P("Cặp kết quả \"nhẹ thua / nặng thắng\" trả lời trực tiếp câu hỏi nghiên cứu và đúng bối cảnh thực tế: model production lớn hơn CifarCNN nhiều lần nên bão hoà GPU và hưởng lợi từ phân tán — miễn là chi phí điều phối được kiểm soát bằng thiết kế đúng (Chương 6) và, ở quy mô lớn hơn, bằng lựa chọn kiến trúc điều phối phù hợp (Chương 8). Rộng hơn, báo cáo minh hoạ một phương pháp luận HPC có thể chuyển giao: đo phân rã để định vị bottleneck, tối ưu đúng chỗ, và diễn giải kết quả qua lăng kính định luật Amdahl."));
body.push(new Paragraph({ children: [new PageBreak()] }));

// ============================================================
// TÀI LIỆU THAM KHẢO
// ============================================================
body.push(H1("Tài liệu tham khảo"));
[
  "McMahan, B., Moore, E., Ramage, D., Hampson, S., & Arcas, B. A. y. (2017). Communication-Efficient Learning of Deep Networks from Decentralized Data (FedAvg). AISTATS.",
  "Amdahl, G. M. (1967). Validity of the single processor approach to achieving large scale computing capabilities. AFIPS Conference Proceedings.",
  "Gustafson, J. L. (1988). Reevaluating Amdahl's Law. Communications of the ACM.",
  "He, K., Zhang, X., Ren, S., & Sun, J. (2016). Deep Residual Learning for Image Recognition (ResNet). CVPR.",
  "Krizhevsky, A. (2009). Learning Multiple Layers of Features from Tiny Images (CIFAR-10). Technical Report, University of Toronto.",
  "Sergeev, A., & Del Balso, M. (2018). Horovod: fast and easy distributed deep learning in TensorFlow. arXiv:1802.05799.",
  "gRPC Authors. gRPC: A high performance, open-source universal RPC framework. https://grpc.io",
  "Google. Protocol Buffers. https://protobuf.dev",
  "PyTorch Authors. torch.distributed — Distributed communication package. https://pytorch.org/docs/stable/distributed.html",
].forEach((r) => body.push(numItem([{ t: r }])));
body.push(spacer());
body.push(PR([{ t: "Phụ lục dữ liệu. ", bold: true, italics: true },
  { t: "Toàn bộ số liệu truy về Report/data/*/round_log.csv (đo bằng perf_counter). Sinh lại hình: analyze_cifar.py (baseline nhẹ), analyze_heavy.py (scaling nặng), analyze_extra.py (hình bổ sung Chương 2/5/6), analyze_allreduce.py (Chương 8). Đo throughput mạng: tools/throughput_test.py.", italics: true }]));
body.push(new Paragraph({ children: [new PageBreak()] }));

// ---- PHỤ LỤC A ----
body.push(H1("Phụ lục A — Bảng tái lập (run-id → số liệu)"));
body.push(P("Mỗi con số trong báo cáo truy về đúng một thư mục run dưới Report/data. Cột \"epoch×round\" ghi local_epochs × num_rounds. Sinh lại hình: python analyze_cifar.py (baseline nhẹ), python analyze_heavy.py (scaling nặng), python analyze_allreduce.py (Chương 8) — chạy bằng python env fedml trực tiếp."));
body.push(table([2280, 3180, 1500, 1080, 1320], [
  ["Kịch bản", "Thư mục run", "Model", "e×round", "Số liệu chính"],
  ["B1 light", "exp_cifar_centralized/m1", "CifarCNN", "2×30", "7,92 s/epoch (tổng 237,6s) · best 81,17%"],
  ["B2 light", "exp_cifar_fed_1machine/m1_rv", "CifarCNN", "2×30", "11,34 s/vòng · best 82,24%"],
  ["B3 light", "exp_cifar_fed_2machine/m1_rv2", "CifarCNN", "2×30", "14,48 s/vòng · best 82,11%"],
  ["Solo heavy", "exp_cifar_heavy_solo/s2", "ResNet-18", "1×2", "train 34,1s/client (mean)"],
  ["B2 heavy", "exp_cifar_heavy_1machine/b2b", "ResNet-18", "1×4", "74,28 s/vòng · train 72,3s"],
  ["B3 heavy", "exp_cifar_heavy_2machine/m1_heavy", "ResNet-18", "1×10", "37,83 s/vòng · acc 84,71%"],
  ["Rendezvous OFF", "exp_cifar_fed_2machine/m1", "CifarCNN", "2×30", "vòng-1 = 89,63 s (cold)"],
  ["Load-bal 45/55 (opt-A)", "exp_cifar_fed_2machine/m1_optB", "CifarCNN", "2×30", "mean |skew| 1,21s"],
  ["B1 fair budget (n=4)", "exp_cifar_centralized/m1_le2fair{,_s1,_s7,_s123}", "CifarCNN", "60 ep", "81,72±0,25% · train 540,8s"],
  ["Fed opt-A B2", "exp_cifar_fed_1machine/m1_opt", "CifarCNN", "2×30", "9,70 s/vòng (eval off-path)"],
  ["Fed opt-A B3", "exp_cifar_fed_2machine/m1_opt5", "CifarCNN", "2×30", "10,56 s/vòng (eval off-path)"],
  ["All-reduce A 1máy (n=4)", "exp_cifar_allreduce/A_s{42,1,7,123}", "CifarCNN", "30×2", "82,06±0,30% · crit-path 212,9s"],
  ["All-reduce A 2máy", "exp_cifar_allreduce/A_2m_s42", "CifarCNN", "30×2", "82,25% · crit-path 210,6s"],
  ["All-reduce B", "exp_cifar_allreduce/B_s42", "CifarCNN", "60 ep", "82,33% · 1575,8s (chậm 7,4×)"],
]));
body.push(P("Số dẫn xuất chính: speedup nặng = 74,28/37,83 = 1,96× (hiệu suất 98%); phân tán nhẹ = 11,34/14,48 = 0,78× (thua, tức chậm 1,28×); GPU contention = T2/T1 = 71,9/34,1 = 2,11× (test localhost; cross-check data commit solo/b2b = 72,3/34,6 = 2,09×); rendezvous vòng-1 89,63s → 10,96s; load-balance |skew| cùng opt-A 1,86s → 1,21s (giảm 37%, over-correct đổi dấu — run baseline no-opt m1_rv2 có |skew| tới 2,57s nhưng đó là mức chưa opt-A, không phải hiệu quả riêng của cân tải); throughput link 281,9 MB/s (2,36 Gbps)."));
body.push(P("Số dẫn xuất all-reduce (Chương 8): Kiểu A vs federated opt-A = 291,0/212,9 = 1,37× (1 máy), 316,8/210,6 = 1,50× (2 máy); accuracy A = 82,06±0,30% (n=4 seed) ≈ federated seed-42 best 82,11% (chênh <0,1pp, trong dải seed); Kiểu B = 1575,8/212,9 = 7,4× chậm hơn A; vs Centralized B1 = 540,8/210,6 = 2,57× (nhưng 1-máy đã đạt 2,54× → chủ yếu là hiệu ứng utilization GPU, không phải phân tán). Sinh lại: python allreduce_train.py --mode A|B ... (xem docstring script cho lệnh 1-máy & 2-máy; backend gloo, cần GLOO_SOCKET_IFNAME + tắt IPv6 khi chạy 2 máy Windows)."));
body.push(new Paragraph({ children: [new PageBreak()] }));

// ---- PHỤ LỤC B ----
body.push(H1("Phụ lục B — Dữ liệu từng vòng (trích)"));
body.push(H2("B.1  B3 nặng (ResNet-18, 2 máy) — run m1_heavy"));
body.push(P("Thời gian tính bằng giây. Chú ý train client-0 (Máy 1, kiêm server) luôn cao hơn client-1 (Máy 2) — straggler hệ thống (§6.4, §4.1). Vòng 1 wallclock thấp hơn do là vòng khởi đầu; steady-state ~37,8 s."));
body.push(table([1560, 2100, 2400, 1650, 1650], [
  ["Vòng", "Accuracy", "round_wallclock (s)", "c0 train (s)", "c1 train (s)"],
  ["1", "12,95%", "30,2", "35,4", "29,3"],
  ["2", "75,40%", "38,0", "36,5", "29,3"],
  ["3", "80,59%", "37,9", "36,7", "29,6"],
  ["4", "82,62%", "37,6", "36,4", "29,4"],
  ["5", "84,26%", "37,6", "36,3", "29,6"],
  ["6", "83,77%", "37,9", "36,6", "29,9"],
  ["7", "83,94%", "37,9", "36,6", "29,8"],
  ["8", "83,97%", "37,9", "36,6", "30,1"],
  ["9", "84,71%", "37,9", "36,6", "30,0"],
]));
body.push(H2("B.2  B3 nhẹ (CifarCNN, 2 máy) — run m1_rv2"));
body.push(P("Vòng 1 đã sạch (10,96 s) nhờ rendezvous. Chênh c0−c1 là mất cân bằng tải mà §6.4 xử lý bằng shard weighting (số skew ở đây là baseline chưa opt-A, cao hơn số 1,86s đã opt-A dùng trong bảng chính §6.4)."));
body.push(table([1560, 2100, 2400, 1650, 1650], [
  ["Vòng", "Accuracy", "round_wallclock (s)", "c0 train (s)", "c1 train (s)"],
  ["1", "63,03%", "10,96", "7,85", "7,41"],
  ["2", "71,85%", "13,80", "10,08", "7,66"],
  ["3", "76,52%", "14,76", "10,71", "7,82"],
  ["4", "77,28%", "15,37", "11,15", "7,74"],
  ["5", "79,10%", "14,41", "10,44", "7,69"],
  ["6", "80,21%", "15,18", "11,10", "7,63"],
  ["7", "80,97%", "14,82", "10,74", "7,81"],
  ["8", "81,10%", "14,92", "10,92", "7,74"],
  ["9", "80,98%", "14,26", "10,16", "7,74"],
  ["10", "80,96%", "13,92", "9,95", "8,44"],
]));

// >>> HẾT NỘI DUNG <<<

// ============================================================
const doc = new Document({
  creator: "Marcus",
  title: "Báo cáo cuối kỳ — HPC for AI: Huấn luyện AI phân tán 2-node",
  features: { updateFields: true }, // Word tự cập nhật TOC khi mở
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
      { reference: "numlist", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.",
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
          new TextRun({ text: "HPC for AI — Huấn luyện AI phân tán 2-node   |   Trang ", size: 18, color: "888888" }),
          new TextRun({ children: [PageNumber.CURRENT], size: 18, color: "888888" }),
        ],
      })] }),
    },
    children: body,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  const out = path.join(__dirname, "Report", "bao_cao_hpc.docx");
  fs.writeFileSync(out, buf);
  console.log("WROTE " + out + " (" + buf.length + " bytes)");
});
