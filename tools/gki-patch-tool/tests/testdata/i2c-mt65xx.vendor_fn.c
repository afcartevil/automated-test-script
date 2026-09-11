static int mtk_i2c_transfer(struct i2c_adapter *adap,
			    struct i2c_msg msgs[], int num)
{
	int ret;
	int left_num = num;
	int i, j;
	u8 *dma_multi_wr_buf;
	struct i2c_msg multi_msg[1];
	struct mtk_i2c *i2c = i2c_get_adapdata(adap);

	ret = mtk_i2c_clock_enable(i2c);
	if (ret)
		return ret;

	/* update qos to prevent deep idle during transfer */
	if (i2c->qos_req)
		cpu_latency_qos_update_request(&i2c->i2c_qos_request, 20);

	if ((i2c->ch_offset_i2c == I2C_OFFSET_AP) && (i2c->timeout_flag == 2)) {
		dev_info(i2c->dev,"%s: i2c->clk_flag=%d, i2c->timeout_flag=%d, i2c->complete_flag=%d\n",
			__func__, i2c->clk_flag, i2c->timeout_flag, i2c->complete_flag);
		dev_info(i2c->dev,"%s: i2c->clk_ex_flag = %d, i2c_complete_t:[%5lu.%06lu]",
			__func__, i2c->clk_ex_flag, (unsigned long)i2c->complete_time, i2c->complete_ns / 1000);
	}

	if (i2c->ch_offset_i2c == I2C_OFFSET_AP) {
		i2c->timeout_flag = 1;
		i2c->complete_flag = 1;
	}


	i2c->master_code_sended = false;
	i2c->auto_restart = i2c->dev_comp->auto_restart;

	/* checking if we can skip restart and optimize using WRRD mode */
	if (i2c->auto_restart && num == 2) {
		if (!(msgs[0].flags & I2C_M_RD) && (msgs[1].flags & I2C_M_RD) &&
		    msgs[0].addr == msgs[1].addr) {
			i2c->auto_restart = 0;
		}
	}

	if (num > 1) {
		for (i = 0; i < num - 1; i++) {
			if (!(msgs[i].flags & I2C_M_RD) && !(msgs[i+1].flags &
				I2C_M_RD) && (msgs[i].addr == msgs[i+1].addr)
					&& (msgs[i].len == msgs[i+1].len)) {
				continue;
			} else
				break;
		}
		if (i >= num - 1) {
			i2c->op = I2C_MASTER_CONTINUOUS_WR;
			j = 0;
			dma_multi_wr_buf = kzalloc(msgs->len * num, GFP_KERNEL);
			if (!dma_multi_wr_buf) {
				ret =  -ENOMEM;
				goto err_exit;
			}
			multi_msg->addr  = msgs->addr;
			multi_msg->len   = msgs->len * num;
			multi_msg->buf   = dma_multi_wr_buf;
			multi_msg->flags  = 0;
			while (j < num) {
				memcpy(dma_multi_wr_buf + msgs->len * j,
							msgs->buf, msgs->len);
				j++;
				msgs++;
				}

			i2c->ignore_restart_irq = false;
			ret = mtk_i2c_do_transfer(i2c, multi_msg, num, 0);
			if (ret < 0)
				goto err_exit;
			ret = num;
				goto err_exit;

		}
	}

	if (i2c->auto_restart && num >= 2 &&
		i2c->speed_hz > I2C_MAX_FAST_MODE_PLUS_FREQ)
		/* ignore the first restart irq after the master code,
		 * otherwise the first transfer will be discarded.
		 */
		i2c->ignore_restart_irq = true;
	else
		i2c->ignore_restart_irq = false;

	while (left_num--) {
		if (!msgs->buf) {
			dev_dbg(i2c->dev, "data buffer is NULL.\n");
			ret = -EINVAL;
			goto err_exit;
		}

		if (msgs->flags & I2C_M_RD)
			i2c->op = I2C_MASTER_RD;
		else
			i2c->op = I2C_MASTER_WR;

		if (!i2c->auto_restart) {
			if (num > 1) {
				/* combined two messages into one transaction */
				i2c->op = I2C_MASTER_WRRD;
				left_num--;
			}
		}

		/* always use DMA mode. */
		ret = mtk_i2c_do_transfer(i2c, msgs, num, left_num);
		if (ret < 0)
			goto err_exit;

		msgs++;
	}
	/* the return value is number of executed messages */
	ret = num;

err_exit:
	if (i2c->qos_req)
		cpu_latency_qos_update_request(&i2c->i2c_qos_request,
			PM_QOS_DEFAULT_VALUE);
	mtk_i2c_clock_disable(i2c);
	return ret;
}

static irqreturn_t mtk_i2c_irq(int irqno, void *dev_id)
{
	struct mtk_i2c *i2c = dev_id;
	u16 restart_flag = 0;
	u16 intr_stat;

	if (i2c->auto_restart)
		restart_flag = I2C_RS_TRANSFER;

	intr_stat = mtk_i2c_readw(i2c, OFFSET_INTR_STAT);
	mtk_i2c_writew(i2c, intr_stat, OFFSET_INTR_STAT);

	if (i2c->ch_offset_i2c == I2C_OFFSET_AP) {
		if ((i2c->timeout_flag == 2) || (i2c->complete_flag == 3)) {
			dev_info(i2c->dev,"%s: i2c->clk_flag=%d, i2c->timeout_flag=%d, i2c->complete_flag=%d\n",
				__func__, i2c->clk_flag, i2c->timeout_flag, i2c->complete_flag);
			dev_info(i2c->dev,"%s: i2c->clk_ex_flag = %d, i2c_complete_t:[%5lu.%06lu]",
				__func__, i2c->clk_ex_flag, (unsigned long)i2c->complete_time, i2c->complete_ns / 1000);
		}
	}
	/*
	 * when occurs ack error, i2c controller generate two interrupts
	 * first is the ack error interrupt, then the complete interrupt
	 * i2c->irq_stat need keep the two interrupt value.
	 */
	i2c->irq_stat |= intr_stat;

	if (i2c->ignore_restart_irq && (i2c->irq_stat & restart_flag)) {
		i2c->ignore_restart_irq = false;
		i2c->irq_stat = 0;
		mtk_i2c_writew(i2c, I2C_RS_MUL_CNFG | I2C_RS_MUL_TRIG |
				    I2C_TRANSAC_START, OFFSET_START);
	} else {
		if (i2c->irq_stat & (I2C_TRANSAC_COMP | restart_flag))
			complete(&i2c->msg_complete);
	}

	return IRQ_HANDLED;
}

static u32 mtk_i2c_functionality(struct i2c_adapter *adap)
{
	if (i2c_check_quirks(adap, I2C_AQ_NO_ZERO_LEN))
		return I2C_FUNC_I2C |
			(I2C_FUNC_SMBUS_EMUL & ~I2C_FUNC_SMBUS_QUICK);
	else
		return I2C_FUNC_I2C | I2C_FUNC_SMBUS_EMUL;
}

static const struct i2c_algorithm mtk_i2c_algorithm = {