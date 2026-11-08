// Таймер, адреса как у CLINT в QEMU (смещения внутри окна 0x0200_0000)
// 0x0000 msip, 0x4000/0x4004 mtimecmp, 0xBFF8/0xBFFC mtime
// TICK_DIV = частота_clk / 10 МГц (50 МГц -> 5)
module clint #(parameter TICK_DIV = 5) (
    input  wire        clk,
    input  wire        rst,
    input  wire        stb,
    input  wire        we,
    input  wire [15:0] addr,
    input  wire [31:0] wdata,
    output reg  [31:0] rdata,
    output wire        ack,
    output wire        irq_timer,
    output wire        irq_sw
);
    assign ack = stb;
    reg [63:0] mtime, mtimecmp;
    reg        msip;
    reg [7:0]  pre;

    assign irq_timer = (mtime >= mtimecmp);
    assign irq_sw    = msip;

    always @(posedge clk) begin
        if (rst) begin
            mtime <= 0; mtimecmp <= {64{1'b1}}; msip <= 0; pre <= 0;
        end else begin
            if (pre == TICK_DIV - 1) begin pre <= 0; mtime <= mtime + 1'b1; end
            else pre <= pre + 1'b1;

            if (stb && we) begin
                case (addr[15:2])
                    14'h0000: msip            <= wdata[0];
                    14'h1000: mtimecmp[31:0]  <= wdata;
                    14'h1001: mtimecmp[63:32] <= wdata;
                    14'h2FFE: mtime[31:0]     <= wdata;
                    14'h2FFF: mtime[63:32]    <= wdata;
                    default: ;
                endcase
            end
        end
    end

    always @* begin
        case (addr[15:2])
            14'h0000: rdata = {31'b0, msip};
            14'h1000: rdata = mtimecmp[31:0];
            14'h1001: rdata = mtimecmp[63:32];
            14'h2FFE: rdata = mtime[31:0];
            14'h2FFF: rdata = mtime[63:32];
            default:  rdata = 32'b0;
        endcase
    end
endmodule