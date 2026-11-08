`timescale 1ns/1ps
module tb;
    reg clk = 0, rst = 1;
    always #5 clk = ~clk;
    integer errors = 0;
    integer n;
    reg [31:0] t;

    // ----- UART: tx замкнут на rx -----
    reg        u_stb = 0, u_we = 0;
    reg  [2:0] u_addr = 0;
    reg  [7:0] u_wd = 0;
    wire [7:0] u_rd;
    wire       u_ack, line;
    uart #(.DIV(8)) u (.clk(clk), .rst(rst), .stb(u_stb), .we(u_we), .addr(u_addr),
                       .wdata(u_wd), .rdata(u_rd), .ack(u_ack), .rx(line), .tx(line));

    // ----- CLINT -----
    reg         c_stb = 0, c_we = 0;
    reg  [15:0] c_addr = 0;
    reg  [31:0] c_wd = 0;
    wire [31:0] c_rd;
    wire        c_ack, irq_t, irq_s;
    clint #(.TICK_DIV(2)) c (.clk(clk), .rst(rst), .stb(c_stb), .we(c_we), .addr(c_addr),
                             .wdata(c_wd), .rdata(c_rd), .ack(c_ack),
                             .irq_timer(irq_t), .irq_sw(irq_s));

    task uwrite(input [2:0] a, input [7:0] d);
        begin
            @(negedge clk); u_stb = 1; u_we = 1; u_addr = a; u_wd = d;
            @(negedge clk); u_stb = 0; u_we = 0;
        end
    endtask

    task uread(input [2:0] a, output [7:0] d);
        begin
            @(negedge clk); u_stb = 1; u_we = 0; u_addr = a; #1; d = u_rd;
            @(negedge clk); u_stb = 0;
        end
    endtask

    task cwrite(input [15:0] a, input [31:0] d);
        begin
            @(negedge clk); c_stb = 1; c_we = 1; c_addr = a; c_wd = d;
            @(negedge clk); c_stb = 0; c_we = 0;
        end
    endtask

    task cread(input [15:0] a, output [31:0] d);
        begin
            @(negedge clk); c_stb = 1; c_we = 0; c_addr = a; #1; d = c_rd;
            @(negedge clk); c_stb = 0;
        end
    endtask

    task uart_xfer(input [7:0] b);
        reg [7:0] d;
        integer k;
        begin
            d = 0; k = 0;
            while (!d[5] && k < 200) begin uread(3'd5, d); k = k + 1; end   // ждём "передатчик свободен"
            uwrite(3'd0, b);
            d = 0; k = 0;
            while (!d[0] && k < 500) begin uread(3'd5, d); k = k + 1; end   // ждём "байт принят"
            if (!d[0]) begin errors = errors + 1; $display("FAIL: uart rx timeout"); end
            uread(3'd0, d);
            if (d !== b) begin errors = errors + 1; $display("FAIL: sent %h got %h", b, d); end
            else $display("uart ok: %h", d);
        end
    endtask

    initial begin
        repeat (4) @(negedge clk);
        rst = 0;

        uart_xfer(8'h41);
        uart_xfer(8'h55);
        uart_xfer(8'hA3);

        cwrite(16'hBFF8, 32'd0);          // mtime = 0
        cwrite(16'hBFFC, 32'd0);
        cwrite(16'h4004, 32'hFFFFFFFF);   // сначала в бесконечность, как делает ядро
        cwrite(16'h4000, 32'd20);
        cwrite(16'h4004, 32'd0);          // порог = 20
        if (irq_t) begin errors = errors + 1; $display("FAIL: irq fired early"); end
        n = 0;
        while (!irq_t && n < 1000) begin @(negedge clk); n = n + 1; end
        if (!irq_t) begin errors = errors + 1; $display("FAIL: no timer irq"); end
        cread(16'hBFF8, t);
        if (t < 20) begin errors = errors + 1; $display("FAIL: mtime=%0d", t); end
        else $display("timer irq ok, mtime=%0d", t);
        cwrite(16'h4004, 32'hFFFFFFFF);   // отодвинули порог, прерывание должно уйти
        @(negedge clk); @(negedge clk);
        if (irq_t) begin errors = errors + 1; $display("FAIL: irq not cleared"); end
        else $display("timer clear ok");

        if (errors == 0) $display("TB PASS");
        else $display("TB FAIL: %0d errors", errors);
        $finish;
    end

    initial begin
        #3000000;
        $display("TB FAIL: global timeout");
        $finish;
    end
endmodule