`timescale 1ns/1ps
module tb_shell;
    localparam BIT = 16;                 // тактов на бит UART
    reg clk = 0, rst = 1, uart_rx = 1;
    always #5 clk = ~clk;
    wire tx;

    soc #(.RAM_AW(12), .INIT_FILE("out/ksim.hex"), .UART_DIV(BIT), .TICK_DIV(2))
        dut (.clk(clk), .rst(rst), .uart_rx(uart_rx), .uart_tx(tx));

    initial begin
        repeat (5) @(posedge clk);
        rst <= 1'b0;
    end

    // консоль: показываем всё, что ядро пишет в UART
    always @(posedge clk) begin
        if (dut.mem_valid && !dut.mem_ready && (|dut.mem_wstrb)) begin
            if (dut.mem_addr == 32'h1000_0000) $write("%c", dut.mem_wdata[7:0]);
            if (dut.mem_addr == 32'h0010_0000) begin
                $display("\nSIM EXIT %h", dut.mem_wdata);
                $finish;
            end
        end
    end

    // "клавиатура": один байт по проводу, 8N1
    task send_byte(input [7:0] b);
        integer j;
        begin
            uart_rx = 1'b0; repeat (BIT) @(posedge clk);
            for (j = 0; j < 8; j = j + 1) begin
                uart_rx = b[j]; repeat (BIT) @(posedge clk);
            end
            uart_rx = 1'b1; repeat (BIT) @(posedge clk);
        end
    endtask

    task send_line(input [8*40-1:0] s);
        integer k;
        reg [7:0] c;
        reg started;
        begin
            started = 1'b0;
            for (k = 39; k >= 0; k = k - 1) begin
                c = s[8*k +: 8];
                if (c != 8'd0) started = 1'b1;
                if (started) begin
                    send_byte(c);
                    repeat (1500) @(posedge clk);
                end
            end
            send_byte(8'h0D);
            repeat (60000) @(posedge clk);
        end
    endtask

    initial begin
        repeat (40000) @(posedge clk);   // дать ядру загрузиться
        send_line("help");
        send_line("ver");
        send_line("echo hi there");
        send_line("uptime");
        send_line("peek 80000000");
        send_line("exit");
    end

    initial begin
        #100000000;
        $display("\nTIMEOUT");
        $finish;
    end
endmodule