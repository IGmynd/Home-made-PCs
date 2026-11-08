`timescale 1ns/1ps
module tb_soc;
    reg clk = 0, rst = 1;
    always #5 clk = ~clk;
    wire tx;

    soc #(.RAM_AW(12), .INIT_FILE("out/selftest.hex"), .UART_DIV(4), .TICK_DIV(2))
        dut (.clk(clk), .rst(rst), .uart_rx(1'b1), .uart_tx(tx));

    initial begin
        repeat (5) @(posedge clk);
        rst <= 1'b0;
    end

    // "консоль" теста: ловим записи на шине
    always @(posedge clk) begin
        if (dut.mem_valid && !dut.mem_ready && (|dut.mem_wstrb)) begin
            if (dut.mem_addr == 32'h1000_0000) $write("%c", dut.mem_wdata[7:0]);
            if (dut.mem_addr == 32'h0010_0000) begin
                $display("\nSIM EXIT %h", dut.mem_wdata);
                $finish;
            end
        end
    end

    initial begin
        #50000000;
        $display("\nTIMEOUT");
        $finish;
    end
endmodule