// Ядро ПТ v0.3: RV32IMC + Zicsr, режим M, многотактовое.
// Шина: mem_valid держится, пока mem_ready не станет 1 (ответ приходит со 2-го такта).
// mem_addr байтовый (не выровнен), mem_wstrb != 0 означает запись.
module cpu #(parameter RESET_ADDR = 32'h8000_0000) (
    input  wire        clk,
    input  wire        rst,
    output reg         mem_valid,
    input  wire        mem_ready,
    output reg  [31:0] mem_addr,
    output reg  [31:0] mem_wdata,
    output reg  [3:0]  mem_wstrb,
    input  wire [31:0] mem_rdata,
    input  wire        irq_timer,
    input  wire        irq_sw,
    input  wire        irq_ext
);
    localparam S_START = 3'd0, S_FETCH = 3'd1, S_EXEC = 3'd2, S_MEM = 3'd3,
               S_MD = 3'd4, S_FETCH2 = 3'd5;

    reg [2:0]  state;
    reg [31:0] pc, ir, eff;
    reg        il4;                  // 1: команда 32-битная, 0: 16-битная
    reg [15:0] fl;                   // нижняя половина команды на стыке слов
    reg [31:0] regs [0:31];

    reg        mstatus_mie, mstatus_mpie;
    reg [31:0] mie_r, mtvec, mscratch, mepc, mcause, mtval;
    reg [63:0] mcycle;

    // умножитель/делитель
    reg [63:0] md_acc, md_m;
    reg [31:0] md_q, md_rem, md_b, md_a;
    reg [5:0]  md_cnt;
    reg        md_div, md_neg;

    integer i;
    initial for (i = 0; i < 32; i = i + 1) regs[i] = 32'd0;

    wire [31:0] pc_inc = pc + (il4 ? 32'd4 : 32'd2);

    // ---------- расширение C: разворот 16-битной команды в 32-битную ----------
    wire [15:0] fh   = pc[1] ? mem_rdata[31:16] : mem_rdata[15:0];
    wire        fh_c = (fh[1:0] != 2'b11);
    wire [4:0]  c_rd   = fh[11:7];
    wire [4:0]  c_rs2  = fh[6:2];
    wire [4:0]  c_rdp  = {2'b01, fh[4:2]};
    wire [4:0]  c_rs1p = {2'b01, fh[9:7]};
    wire [11:0] c_i6   = {{6{fh[12]}}, fh[12], fh[6:2]};
    wire [9:0]  c_nz4  = {fh[10:7], fh[12:11], fh[5], fh[6], 2'b00};
    wire [6:0]  c_uw   = {fh[5], fh[12:10], fh[6], 2'b00};
    wire [9:0]  c_nz16 = {fh[12], fh[4:3], fh[5], fh[2], fh[6], 4'b0000};
    wire [7:0]  c_ulw  = {fh[3:2], fh[12], fh[6:4], 2'b00};
    wire [7:0]  c_usw  = {fh[8:7], fh[12:9], 2'b00};
    wire [20:0] c_j    = {{9{fh[12]}}, fh[12], fh[8], fh[10:9], fh[6], fh[7], fh[2], fh[11], fh[5:3], 1'b0};
    wire [12:0] c_b    = {{4{fh[12]}}, fh[12], fh[6:5], fh[2], fh[11:10], fh[4:3], 1'b0};

    reg [31:0] cx;      // развёрнутая команда
    reg        cill;    // сжатая команда недопустима
    always @* begin
        cx = 32'hFFFF_FFFF;
        cill = 1'b0;
        case (fh[1:0])
        2'b00: begin
            case (fh[15:13])
                3'b000: begin
                    cx = {2'b00, c_nz4, 5'd2, 3'b000, c_rdp, 7'b0010011};          // c.addi4spn
                    cill = (c_nz4 == 10'd0);
                end
                3'b010: cx = {5'd0, c_uw, c_rs1p, 3'b010, c_rdp, 7'b0000011};      // c.lw
                3'b110: cx = {5'd0, c_uw[6:5], c_rdp, c_rs1p, 3'b010, c_uw[4:0], 7'b0100011}; // c.sw
                default: cill = 1'b1;
            endcase
        end
        2'b01: begin
            case (fh[15:13])
                3'b000: cx = {c_i6, c_rd, 3'b000, c_rd, 7'b0010011};               // c.addi / c.nop
                3'b001: cx = {c_j[20], c_j[10:1], c_j[11], c_j[19:12], 5'd1, 7'b1101111}; // c.jal
                3'b010: cx = {c_i6, 5'd0, 3'b000, c_rd, 7'b0010011};               // c.li
                3'b011: begin
                    if (c_rd == 5'd2) begin                                         // c.addi16sp
                        cx = {{2{c_nz16[9]}}, c_nz16, 5'd2, 3'b000, 5'd2, 7'b0010011};
                        cill = (c_nz16 == 10'd0);
                    end else begin                                                  // c.lui
                        cx = {{15{fh[12]}}, fh[6:2], c_rd, 7'b0110111};
                        cill = ({fh[12], fh[6:2]} == 6'd0);
                    end
                end
                3'b100: begin
                    case (fh[11:10])
                        2'b00: begin cx = {7'b0000000, fh[6:2], c_rs1p, 3'b101, c_rs1p, 7'b0010011}; cill = fh[12]; end // c.srli
                        2'b01: begin cx = {7'b0100000, fh[6:2], c_rs1p, 3'b101, c_rs1p, 7'b0010011}; cill = fh[12]; end // c.srai
                        2'b10: cx = {c_i6, c_rs1p, 3'b111, c_rs1p, 7'b0010011};                                         // c.andi
                        default: begin
                            cill = fh[12];
                            case (fh[6:5])
                                2'b00:   cx = {7'b0100000, c_rdp, c_rs1p, 3'b000, c_rs1p, 7'b0110011};  // c.sub
                                2'b01:   cx = {7'b0000000, c_rdp, c_rs1p, 3'b100, c_rs1p, 7'b0110011};  // c.xor
                                2'b10:   cx = {7'b0000000, c_rdp, c_rs1p, 3'b110, c_rs1p, 7'b0110011};  // c.or
                                default: cx = {7'b0000000, c_rdp, c_rs1p, 3'b111, c_rs1p, 7'b0110011};  // c.and
                            endcase
                        end
                    endcase
                end
                3'b101: cx = {c_j[20], c_j[10:1], c_j[11], c_j[19:12], 5'd0, 7'b1101111}; // c.j
                3'b110: cx = {c_b[12], c_b[10:5], 5'd0, c_rs1p, 3'b000, c_b[4:1], c_b[11], 7'b1100011}; // c.beqz
                default: cx = {c_b[12], c_b[10:5], 5'd0, c_rs1p, 3'b001, c_b[4:1], c_b[11], 7'b1100011}; // c.bnez
            endcase
        end
        2'b10: begin
            case (fh[15:13])
                3'b000: begin cx = {7'b0000000, c_rs2, c_rd, 3'b001, c_rd, 7'b0010011}; cill = fh[12]; end // c.slli
                3'b010: begin cx = {4'b0000, c_ulw, 5'd2, 3'b010, c_rd, 7'b0000011}; cill = (c_rd == 5'd0); end // c.lwsp
                3'b100: begin
                    if (!fh[12]) begin
                        if (c_rs2 == 5'd0) begin                                    // c.jr
                            cx = {12'd0, c_rd, 3'b000, 5'd0, 7'b1100111};
                            cill = (c_rd == 5'd0);
                        end else cx = {7'b0000000, c_rs2, 5'd0, 3'b000, c_rd, 7'b0110011}; // c.mv
                    end else begin
                        if (c_rd == 5'd0 && c_rs2 == 5'd0) cx = 32'h0010_0073;      // c.ebreak
                        else if (c_rs2 == 5'd0) cx = {12'd0, c_rd, 3'b000, 5'd1, 7'b1100111}; // c.jalr
                        else cx = {7'b0000000, c_rs2, c_rd, 3'b000, c_rd, 7'b0110011};        // c.add
                    end
                end
                3'b110: cx = {4'b0000, c_usw[7:5], c_rs2, 5'd2, 3'b010, c_usw[4:0], 7'b0100011}; // c.swsp
                default: cill = 1'b1;
            endcase
        end
        default: ;
        endcase
    end

    // ---------- разбор инструкции ----------
    wire [6:0]  opcode = ir[6:0];
    wire [4:0]  rd  = ir[11:7];
    wire [2:0]  f3  = ir[14:12];
    wire [4:0]  rs1 = ir[19:15];
    wire [4:0]  rs2 = ir[24:20];
    wire [31:0] rs1v = (rs1 == 5'd0) ? 32'd0 : regs[rs1];
    wire [31:0] rs2v = (rs2 == 5'd0) ? 32'd0 : regs[rs2];
    wire signed [31:0] rs1s = rs1v;
    wire signed [31:0] rs2s = rs2v;

    wire [31:0] immI = {{20{ir[31]}}, ir[31:20]};
    wire [31:0] immS = {{20{ir[31]}}, ir[31:25], ir[11:7]};
    wire [31:0] immB = {{19{ir[31]}}, ir[31], ir[7], ir[30:25], ir[11:8], 1'b0};
    wire [31:0] immU = {ir[31:12], 12'b0};
    wire [31:0] immJ = {{11{ir[31]}}, ir[31], ir[19:12], ir[20], ir[30:21], 1'b0};

    // ---------- АЛУ ----------
    wire is_op = (opcode == 7'b0110011);
    wire [31:0] alu_b = is_op ? rs2v : immI;
    wire signed [31:0] alu_bs = alu_b;
    wire [4:0]  shamt = alu_b[4:0];
    wire [31:0] sra_res = rs1s >>> shamt;
    reg  [31:0] alu_out;
    always @* begin
        case (f3)
            3'd0:    alu_out = (is_op && ir[30]) ? (rs1v - alu_b) : (rs1v + alu_b);
            3'd1:    alu_out = rs1v << shamt;
            3'd2:    alu_out = (rs1s < alu_bs) ? 32'd1 : 32'd0;
            3'd3:    alu_out = (rs1v < alu_b) ? 32'd1 : 32'd0;
            3'd4:    alu_out = rs1v ^ alu_b;
            3'd5:    alu_out = ir[30] ? sra_res : (rs1v >> shamt);
            3'd6:    alu_out = rs1v | alu_b;
            default: alu_out = rs1v & alu_b;
        endcase
    end
    wire f7_0  = (ir[31:25] == 7'b0000000);
    wire f7_20 = (ir[31:25] == 7'b0100000);
    wire alu_legal = is_op ? (f7_0 || (f7_20 && (f3 == 3'd0 || f3 == 3'd5)))
                   : (f3 == 3'd1) ? f7_0
                   : (f3 == 3'd5) ? (f7_0 || f7_20)
                   : 1'b1;

    // ---------- расширение M: подготовка операндов ----------
    wire is_m = is_op && (ir[31:25] == 7'b0000001);
    wire mul_na = (f3 == 3'd1 || f3 == 3'd2) && rs1v[31];
    wire mul_nb = (f3 == 3'd1) && rs2v[31];
    wire [31:0] mul_ua = mul_na ? (32'd0 - rs1v) : rs1v;
    wire [31:0] mul_ub = mul_nb ? (32'd0 - rs2v) : rs2v;
    wire div_signed = ~f3[0];
    wire div_na = div_signed && rs1v[31];
    wire div_nb = div_signed && rs2v[31];
    wire [31:0] div_ua = div_na ? (32'd0 - rs1v) : rs1v;
    wire [31:0] div_ub = div_nb ? (32'd0 - rs2v) : rs2v;

    // ---------- расширение M: шаги и результат ----------
    wire [32:0] div_shift  = {md_rem, md_q[31]};
    wire        div_sub_ok = (div_shift >= {1'b0, md_b});
    wire [32:0] div_diff   = div_shift - {1'b0, md_b};
    wire [63:0] mul_p = md_neg ? (64'd0 - md_acc) : md_acc;
    wire [31:0] quo   = md_neg ? (32'd0 - md_q)   : md_q;
    wire [31:0] remd  = md_neg ? (32'd0 - md_rem) : md_rem;
    reg  [31:0] md_result;
    always @* begin
        if (!md_div)              md_result = (f3 == 3'd0) ? mul_p[31:0] : mul_p[63:32];
        else if (md_b == 32'd0)   md_result = f3[1] ? md_a : 32'hFFFF_FFFF;
        else if (f3[1])           md_result = remd;
        else                      md_result = quo;
    end

    // ---------- переходы ----------
    reg br_take;
    always @* begin
        case (f3)
            3'd0:    br_take = (rs1v == rs2v);
            3'd1:    br_take = (rs1v != rs2v);
            3'd4:    br_take = (rs1s <  rs2s);
            3'd5:    br_take = (rs1s >= rs2s);
            3'd6:    br_take = (rs1v <  rs2v);
            3'd7:    br_take = (rs1v >= rs2v);
            default: br_take = 1'b0;
        endcase
    end
    wire br_legal = (f3 != 3'd2) && (f3 != 3'd3);
    wire [31:0] br_target   = pc + immB;
    wire [31:0] jal_target  = pc + immJ;
    wire [31:0] jalr_target = (rs1v + immI) & 32'hFFFF_FFFE;

    // ---------- память ----------
    wire [31:0] ea_l = rs1v + immI;
    wire [31:0] ea_s = rs1v + immS;
    wire ld_legal = (f3 == 3'd0) || (f3 == 3'd1) || (f3 == 3'd2) || (f3 == 3'd4) || (f3 == 3'd5);
    wire st_legal = (f3 == 3'd0) || (f3 == 3'd1) || (f3 == 3'd2);
    wire ld_mis = ((f3[1:0] == 2'd1) && ea_l[0]) || ((f3[1:0] == 2'd2) && (ea_l[1:0] != 2'd0));
    wire st_mis = ((f3[1:0] == 2'd1) && ea_s[0]) || ((f3[1:0] == 2'd2) && (ea_s[1:0] != 2'd0));
    wire [31:0] st_data = rs2v << {ea_s[1:0], 3'b000};
    wire [3:0]  st_strb = (f3[1:0] == 2'd0) ? (4'b0001 << ea_s[1:0]) :
                          (f3[1:0] == 2'd1) ? (4'b0011 << ea_s[1:0]) : 4'b1111;
    wire [31:0] ld_sh = mem_rdata >> {eff[1:0], 3'b000};
    reg  [31:0] load_val;
    always @* begin
        case (f3)
            3'd0:    load_val = {{24{ld_sh[7]}},  ld_sh[7:0]};
            3'd1:    load_val = {{16{ld_sh[15]}}, ld_sh[15:0]};
            3'd2:    load_val = mem_rdata;
            3'd4:    load_val = {24'b0, ld_sh[7:0]};
            default: load_val = {16'b0, ld_sh[15:0]};
        endcase
    end

    // ---------- CSR ----------
    wire [31:0] mip = {20'b0, irq_ext, 3'b0, irq_timer, 3'b0, irq_sw, 3'b0};
    reg  [31:0] csr_old;
    reg         csr_ok;
    always @* begin
        csr_ok = 1'b1;
        case (ir[31:20])
            12'h300: csr_old = {19'b0, 2'b11, 3'b0, mstatus_mpie, 3'b0, mstatus_mie, 3'b0};
            12'h301: csr_old = 32'h4000_1104;       // misa: RV32 I M C
            12'h304: csr_old = mie_r;
            12'h305: csr_old = mtvec;
            12'h340: csr_old = mscratch;
            12'h341: csr_old = mepc;
            12'h342: csr_old = mcause;
            12'h343: csr_old = mtval;
            12'h344: csr_old = mip;
            12'hB00: csr_old = mcycle[31:0];
            12'hB80: csr_old = mcycle[63:32];
            12'hF14: csr_old = 32'd0;               // mhartid
            default: begin csr_old = 32'd0; csr_ok = 1'b0; end
        endcase
    end
    wire [31:0] csr_src = f3[2] ? {27'b0, rs1} : rs1v;
    reg  [31:0] csr_new;
    always @* begin
        case (f3[1:0])
            2'd1:    csr_new = csr_src;
            2'd2:    csr_new = csr_old | csr_src;
            default: csr_new = csr_old & ~csr_src;
        endcase
    end
    wire csr_we = (f3[1:0] == 2'd1) || (rs1 != 5'd0);

    // ---------- прерывания ----------
    wire [31:0] pend = mip & mie_r;
    wire take_irq = mstatus_mie && (pend != 32'd0);
    wire [31:0] irq_cause = pend[11] ? 32'd11 : pend[3] ? 32'd3 : 32'd7;

    // ---------- вспомогательные задачи ----------
    task trap(input [31:0] cause, input [31:0] epc, input [31:0] tval);
        begin
            mepc <= epc; mcause <= cause; mtval <= tval;
            mstatus_mpie <= mstatus_mie; mstatus_mie <= 1'b0;
            pc <= mtvec; state <= S_START; mem_valid <= 1'b0;
        end
    endtask

    task wr(input [4:0] r, input [31:0] v);
        begin
            if (r != 5'd0) regs[r] <= v;
        end
    endtask

    // ---------- основной автомат ----------
    always @(posedge clk) begin
        if (rst) begin
            state <= S_START; pc <= RESET_ADDR; ir <= 32'd0; eff <= 32'd0;
            il4 <= 1'b1; fl <= 16'd0;
            mem_valid <= 1'b0; mem_addr <= 32'd0; mem_wdata <= 32'd0; mem_wstrb <= 4'd0;
            mstatus_mie <= 1'b0; mstatus_mpie <= 1'b0;
            mie_r <= 32'd0; mtvec <= 32'd0; mscratch <= 32'd0;
            mepc <= 32'd0; mcause <= 32'd0; mtval <= 32'd0; mcycle <= 64'd0;
            md_acc <= 64'd0; md_m <= 64'd0; md_q <= 32'd0; md_rem <= 32'd0;
            md_b <= 32'd0; md_a <= 32'd0; md_cnt <= 6'd0; md_div <= 1'b0; md_neg <= 1'b0;
        end else begin
            mcycle <= mcycle + 64'd1;
            case (state)
            S_START: begin
                if (take_irq) begin
                    trap(32'h8000_0000 | irq_cause, pc, 32'd0);
                end else begin
                    mem_valid <= 1'b1; mem_addr <= {pc[31:2], 2'b00}; mem_wstrb <= 4'd0;
                    state <= S_FETCH;
                end
            end

            S_FETCH: begin
                if (mem_ready) begin
                    if (fh_c) begin                                 // 16-битная команда
                        ir <= cill ? 32'hFFFF_FFFF : cx; il4 <= 1'b0;
                        mem_valid <= 1'b0; state <= S_EXEC;
                    end else if (!pc[1]) begin                      // 32-битная, выровнена
                        ir <= mem_rdata; il4 <= 1'b1;
                        mem_valid <= 1'b0; state <= S_EXEC;
                    end else begin                                  // 32-битная на стыке слов
                        fl <= fh;
                        mem_addr <= {pc[31:2], 2'b00} + 32'd4;
                        state <= S_FETCH2;                          // mem_valid остаётся 1
                    end
                end
            end

            S_FETCH2: begin
                if (mem_ready) begin
                    ir <= {mem_rdata[15:0], fl}; il4 <= 1'b1;
                    mem_valid <= 1'b0; state <= S_EXEC;
                end
            end

            S_EXEC: begin
                state <= S_START;
                case (opcode)
                7'b0110111: begin wr(rd, immU); pc <= pc_inc; end              // LUI
                7'b0010111: begin wr(rd, pc + immU); pc <= pc_inc; end         // AUIPC
                7'b1101111: begin wr(rd, pc_inc); pc <= jal_target; end        // JAL
                7'b1100111: begin wr(rd, pc_inc); pc <= jalr_target; end       // JALR
                7'b1100011: begin                                              // ветвления
                    if (!br_legal) trap(32'd2, pc, ir);
                    else if (br_take) pc <= br_target;
                    else pc <= pc_inc;
                end
                7'b0000011: begin                                              // LOAD
                    if (!ld_legal) trap(32'd2, pc, ir);
                    else if (ld_mis) trap(32'd4, pc, ea_l);
                    else begin
                        eff <= ea_l; mem_addr <= ea_l; mem_wstrb <= 4'd0;
                        mem_valid <= 1'b1; state <= S_MEM;
                    end
                end
                7'b0100011: begin                                              // STORE
                    if (!st_legal) trap(32'd2, pc, ir);
                    else if (st_mis) trap(32'd6, pc, ea_s);
                    else begin
                        eff <= ea_s; mem_addr <= ea_s;
                        mem_wdata <= st_data; mem_wstrb <= st_strb;
                        mem_valid <= 1'b1; state <= S_MEM;
                    end
                end
                7'b0010011, 7'b0110011: begin                                  // АЛУ и M
                    if (is_m) begin
                        md_a <= rs1v; md_cnt <= 6'd32; md_div <= f3[2];
                        md_acc <= 64'd0; md_rem <= 32'd0;
                        if (!f3[2]) begin
                            md_neg <= mul_na ^ mul_nb;
                            md_m <= {32'd0, mul_ua}; md_q <= mul_ub; md_b <= 32'd0;
                        end else begin
                            md_neg <= f3[1] ? div_na : (div_na ^ div_nb);
                            md_q <= div_ua; md_b <= div_ub; md_m <= 64'd0;
                        end
                        state <= S_MD;
                    end else if (alu_legal) begin
                        wr(rd, alu_out); pc <= pc_inc;
                    end else trap(32'd2, pc, ir);
                end
                7'b0001111: pc <= pc_inc;                                      // FENCE = nop
                7'b1110011: begin                                              // SYSTEM
                    if (f3 == 3'd0) begin
                        case (ir[31:20])
                            12'h000: trap(32'd11, pc, 32'd0);                  // ecall
                            12'h001: trap(32'd3, pc, 32'd0);                   // ebreak
                            12'h302: begin                                     // mret
                                pc <= mepc;
                                mstatus_mie <= mstatus_mpie; mstatus_mpie <= 1'b1;
                            end
                            12'h105: pc <= pc_inc;                             // wfi = nop
                            default: trap(32'd2, pc, ir);
                        endcase
                    end else if (f3 == 3'd4 || !csr_ok) begin
                        trap(32'd2, pc, ir);
                    end else begin
                        wr(rd, csr_old);
                        if (csr_we) begin
                            case (ir[31:20])
                                12'h300: begin mstatus_mie <= csr_new[3]; mstatus_mpie <= csr_new[7]; end
                                12'h304: mie_r <= csr_new & 32'h0000_0888;
                                12'h305: mtvec <= {csr_new[31:2], 2'b00};
                                12'h340: mscratch <= csr_new;
                                12'h341: mepc <= {csr_new[31:1], 1'b0};
                                12'h342: mcause <= csr_new;
                                12'h343: mtval <= csr_new;
                                default: ;
                            endcase
                        end
                        pc <= pc_inc;
                    end
                end
                default: trap(32'd2, pc, ir);                                  // неизвестная команда
                endcase
            end

            S_MEM: begin
                if (mem_ready) begin
                    mem_valid <= 1'b0; mem_wstrb <= 4'd0;
                    state <= S_START; pc <= pc_inc;
                    if (opcode == 7'b0000011) wr(rd, load_val);
                end
            end

            S_MD: begin
                if (md_cnt != 6'd0) begin
                    md_cnt <= md_cnt - 6'd1;
                    if (!md_div) begin
                        if (md_q[0]) md_acc <= md_acc + md_m;
                        md_m <= md_m << 1;
                        md_q <= md_q >> 1;
                    end else begin
                        if (div_sub_ok) begin
                            md_rem <= div_diff[31:0]; md_q <= {md_q[30:0], 1'b1};
                        end else begin
                            md_rem <= div_shift[31:0]; md_q <= {md_q[30:0], 1'b0};
                        end
                    end
                end else begin
                    wr(rd, md_result);
                    pc <= pc_inc; state <= S_START;
                end
            end
            endcase
        end
    end
endmodule