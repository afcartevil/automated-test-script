# Qualcomm ADSP Power/USB 分诊 Reference

## 决策树（固件内）

```text
是否 Qualcomm ADSP battman？
  否 -> 不用本 skill
  是 -> 现象主语是什么？

「CC/alert/SOP/swap/PPS/UCSI/glink/ConnectorStatus」为主
  -> qualcomm-adsp-usb-pd-analysis
     从 TCPC IRQ 或 dpm_set_request_to_lpm 起步

「APSD/DCP/QC/UFCS/RFC/TFCP/ICM/慢插」为主
  -> qualcomm-adsp-charging-analysis
     从 charger_detection + dpm_handle_cable_event 起步

两者交织且无法定性
  -> 先看 dpm_handle_cable_event 是否被调用、PortStatus 是否更新
     -> 若 LPM/async 异常 -> usb-pd skill
     -> 若识别链/ICM 异常 -> charging skill
```

## 与两条深挖 skill 的依赖关系

- **usb-pd**：必须先满足「ALERT/PM_REQUEST/ASYNC_EVENT」三条主线之一有证据，再下结论。
- **charging**：必须先区分 `PD active` 与 legacy 支路，再谈 APSD/QC/RFC。

## 不覆盖范围

- Kernel `dwc3` / `usb_role_switch` / gadget 枚举：需在 AP/kernel 日志另行对齐。
- 非高通平台：不使用本目录下 skill。
