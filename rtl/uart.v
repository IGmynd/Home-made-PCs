// UART, регистры как у 16550 (минимум): 0 = THR/RBR, 5 = LSR
// DIV = частота_clk / скорость (50 МГц / 115200 ~ 434)
module uart #(parameter DIV = 434) (
    input  wire       clk,
    input  wire       rst,
    input  wire       stb,
    input  wire       we,
    input  wire [2:0] addr,
    input  wire [7:0] wdata,
    output reg  [7:0] rdata,
    output wire       ack,
    input  wire       rx,
    output reg        tx
);
    assign ack = stb;

    // ---------- передатчик ----------
    reg [8:0]  tx_sh;
    reg [3:0]  tx_cnt;
    reg [15:0] tx_div;
    wire tx_busy = (tx_cnt != 0);

    always @(posedge clk) begin
        if (rst) begin
            tx <= 1'b1; tx_cnt <= 0; tx_div <= 0; tx_sh <= 9'h1FF;
        end else if (!tx_busy) begin
            if (stb && we && addr == 3'd0) begin
                tx     <= 1'b0;                 // старт-бит
                tx_sh  <= {1'b1, wdata};        // данные + стоп-бит
                tx_cnt <= 4'd10;
                tx_div <= DIV - 1;
            end
        end else if (tx_div == 0) begin
            tx     <= tx_sh[0];
            tx_sh  <= {1'b1, tx_sh[8:1]};
            tx_cnt <= tx_cnt - 1'b1;
            tx_div <= DIV - 1;
        end else begin
            tx_div <= tx_div - 1'b1;
        end
    end

    // ---------- приёмник ----------
    reg rx0, rx1;
    always @(posedge clk) begin rx0 <= rx; rx1 <= rx0; end

    reg [3:0]  rx_cnt;
    reg [15:0] rx_div;
    reg [7:0]  rx_sh, rx_data;
    reg        rx_valid;

    always @(posedge clk) begin
        if (rst) begin
            rx_cnt <= 0; rx_div <= 0; rx_valid <= 0; rx_data <= 0; rx_sh <= 0;
        end else begin
            if (stb && !we && addr == 3'd0) rx_valid <= 1'b0;   // чтение забирает байт
            if (rx_cnt == 0) begin
                if (!rx1) begin                                  // начался старт-бит
                    rx_cnt <= 4'd1;
                    rx_div <= DIV + DIV/2 - 4;                   // до середины бита 0
                end
            end else if (rx_div != 0) begin
                rx_div <= rx_div - 1'b1;
            end else begin
                rx_div <= DIV - 1;
                if (rx_cnt <= 4'd7) begin
                    rx_sh  <= {rx1, rx_sh[7:1]};
                    rx_cnt <= rx_cnt + 1'b1;
                end else if (rx_cnt == 4'd8) begin
                    rx_data  <= {rx1, rx_sh[7:1]};
                    rx_valid <= 1'b1;
                    rx_cnt   <= 4'd9;
                end else begin
                    rx_cnt <= 0;                                 // середина стоп-бита, ждём новый байт
                end
            end
        end
    end

    always @* begin
        case (addr)
            3'd0:    rdata = rx_data;
            3'd5:    rdata = {1'b0, ~tx_busy, ~tx_busy, 4'b0000, rx_valid};
            default: rdata = 8'h00;
        endcase
    end
endmodule