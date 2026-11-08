// SoC: ядро + ОЗУ + UART + таймер. Карта памяти как в QEMU:
// 0x0200_0000 CLINT, 0x1000_0000 UART, 0x8000_0000 ОЗУ
module soc #(
    parameter RAM_AW    = 12,        // слов = 2^RAM_AW (12 -> 16 КБ)
    parameter INIT_FILE = "",
    parameter UART_DIV  = 434,
    parameter TICK_DIV  = 5
) (
    input  wire clk,
    input  wire rst,
    input  wire uart_rx,
    output wire uart_tx
);
    wire        mem_valid;
    reg         mem_ready;
    wire [31:0] mem_addr, mem_wdata, mem_rdata;
    wire [3:0]  mem_wstrb;
    wire        irq_t, irq_s;

    cpu cpu0 (
        .clk(clk), .rst(rst),
        .mem_valid(mem_valid), .mem_ready(mem_ready),
        .mem_addr(mem_addr), .mem_wdata(mem_wdata), .mem_wstrb(mem_wstrb),
        .mem_rdata(mem_rdata),
        .irq_timer(irq_t), .irq_sw(irq_s), .irq_ext(1'b0)
    );

    wire xfer      = mem_valid && !mem_ready;       // первый такт обращения
    wire sel_ram   = (mem_addr[31:16] == 16'h8000);
    wire sel_uart  = (mem_addr[31:12] == 20'h10000);
    wire sel_clint = (mem_addr[31:16] == 16'h0200);

    always @(posedge clk) begin
        if (rst) mem_ready <= 1'b0;
        else     mem_ready <= xfer;
    end

    // ---------- ОЗУ ----------
    reg [31:0] ram [0:(1 << RAM_AW) - 1];
    reg [31:0] ram_rd;
    wire [RAM_AW-1:0] ram_idx = mem_addr[RAM_AW+1:2];
    integer k;
    initial begin
        for (k = 0; k < (1 << RAM_AW); k = k + 1) ram[k] = 32'd0;
        if (INIT_FILE != "") $readmemh(INIT_FILE, ram);
    end
    always @(posedge clk) begin
        if (xfer && sel_ram) begin
            if (mem_wstrb[0]) ram[ram_idx][7:0]   <= mem_wdata[7:0];
            if (mem_wstrb[1]) ram[ram_idx][15:8]  <= mem_wdata[15:8];
            if (mem_wstrb[2]) ram[ram_idx][23:16] <= mem_wdata[23:16];
            if (mem_wstrb[3]) ram[ram_idx][31:24] <= mem_wdata[31:24];
            ram_rd <= ram[ram_idx];
        end
    end

    // ---------- UART ----------
    wire [7:0]  uart_rd;
    wire        uart_ack;
    wire [31:0] uart_wd32 = mem_wdata >> {mem_addr[1:0], 3'b000};
    uart #(.DIV(UART_DIV)) uart0 (
        .clk(clk), .rst(rst),
        .stb(xfer && sel_uart), .we(|mem_wstrb),
        .addr(mem_addr[2:0]), .wdata(uart_wd32[7:0]),
        .rdata(uart_rd), .ack(uart_ack),
        .rx(uart_rx), .tx(uart_tx)
    );

    // ---------- CLINT ----------
    wire [31:0] clint_rd;
    wire        clint_ack;
    clint #(.TICK_DIV(TICK_DIV)) clint0 (
        .clk(clk), .rst(rst),
        .stb(xfer && sel_clint), .we(|mem_wstrb),
        .addr(mem_addr[15:0]), .wdata(mem_wdata),
        .rdata(clint_rd), .ack(clint_ack),
        .irq_timer(irq_t), .irq_sw(irq_s)
    );

    // байт UART кладём во все 4 дорожки: ядро само выберет нужную по адресу
    assign mem_rdata = sel_ram   ? ram_rd :
                       sel_uart  ? {4{uart_rd}} :
                       sel_clint ? clint_rd : 32'd0;
endmodule