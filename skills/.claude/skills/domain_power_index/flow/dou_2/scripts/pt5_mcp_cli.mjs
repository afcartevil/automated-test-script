#!/usr/bin/env node
/**
 * CLI wrapper around pt5-mcp-server's official Monsoon PT5 parser.
 * Used by pt5_reader.py so DOU scripts share the same parser as MCP tool "pt5".
 */
import { createRequire } from "module";
import { pathToFileURL } from "url";
import fs from "fs";
import os from "path";

const require = createRequire(import.meta.url);

function resolveParserModule() {
  try {
    return require.resolve("pt5-mcp-server/build/pt5-parser.js");
  } catch {
    /* fall through */
  }
  const appData = process.env.APPDATA || "";
  const candidates = [
    appData ? os.join(appData, "npm", "node_modules", "pt5-mcp-server", "build", "pt5-parser.js") : "",
    os.join(process.env.HOME || "", ".npm-global", "lib", "node_modules", "pt5-mcp-server", "build", "pt5-parser.js"),
    "/usr/local/lib/node_modules/pt5-mcp-server/build/pt5-parser.js",
  ].filter(Boolean);
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  throw new Error(
    "未找到 pt5-mcp-server。请先执行: npm install -g pt5-mcp-server（与 Cursor MCP 配置 pt5 相同）"
  );
}

async function loadParser() {
  const modulePath = resolveParserModule();
  return import(pathToFileURL(modulePath).href);
}

const HEADER_OFFSET = 0;
const STATUS_OFFSET = 272;
const SAMPLE_OFFSET = 1024;
const MISSING_RAW_CURRENT_INT32 = 0x00008001;
const CHAN_MAIN = 0x1000;
const CHAN_USB = 0x2000;
const CHAN_AUX = 0x4000;
const LARGE_FILE_BYTES = 50 * 1024 * 1024;

class SeqReader {
  constructor(buf, startPos = 0) {
    this.buf = buf;
    this.pos = startPos;
  }
  readByte() {
    const v = this.buf.readUInt8(this.pos);
    this.pos += 1;
    return v;
  }
  readSByte() {
    const v = this.buf.readInt8(this.pos);
    this.pos += 1;
    return v;
  }
  readInt16() {
    const v = this.buf.readInt16LE(this.pos);
    this.pos += 2;
    return v;
  }
  readUInt16() {
    const v = this.buf.readUInt16LE(this.pos);
    this.pos += 2;
    return v;
  }
  readInt32() {
    const v = this.buf.readInt32LE(this.pos);
    this.pos += 4;
    return v;
  }
  readUInt32() {
    const v = this.buf.readUInt32LE(this.pos);
    this.pos += 4;
    return v;
  }
  readInt64() {
    const v = this.buf.readBigInt64LE(this.pos);
    this.pos += 8;
    return v;
  }
  readUInt64() {
    const v = this.buf.readBigUInt64LE(this.pos);
    this.pos += 8;
    return v;
  }
  readSingle() {
    const v = this.buf.readFloatLE(this.pos);
    this.pos += 4;
    return v;
  }
  readString() {
    const contentLen = this.readByte();
    const bytes = [];
    for (let i = 0; i < contentLen; i += 1) bytes.push(this.readByte());
    return Buffer.from(bytes).toString("ascii").trim();
  }
}

/** 仅解析 header/status，不加载全部采样点（大 pt5 防 OOM）。 */
function parsePt5MetaLight(buf) {
  const reader = new SeqReader(buf, 4);
  const name = reader.readString();
  if (name !== "Power Tool" && name !== "PowerTool") {
    throw new Error(`Invalid PT5 file: expected "Power Tool", got "${name}"`);
  }
  const header = parseHeader(new SeqReader(buf, HEADER_OFFSET));
  const status = parseStatusPacket(new SeqReader(buf, STATUS_OFFSET));
  const sampleRateHz = status.sampleRate * 1000;
  return { header, status, sampleRateHz };
}

function parseHeader(reader) {
  reader.pos = HEADER_OFFSET;
  const headSize = reader.readInt32();
  const name = reader.readString();
  const batterySize = reader.readInt32();
  const captureDate = reader.readInt64();
  const serialNumber = reader.readString();
  const calibrationStatus = reader.readInt32();
  const voutSetting = reader.readInt32();
  const voutValue = reader.readSingle();
  const hardwareRate = reader.readInt32();
  reader.readSingle();
  const powerField = reader.readInt32();
  const currentField = reader.readInt32();
  const voltageField = reader.readInt32();
  const captureSetting = reader.readString();
  const swVersion = reader.readString();
  const runMode = reader.readInt32();
  const exitCode = reader.readInt32();
  const totalCount = reader.readInt64();
  const statusOffset = reader.readUInt16();
  const statusSize = reader.readUInt16();
  const sampleOffset = reader.readUInt16();
  const sampleSize = reader.readUInt16();
  const initialMainVoltage = reader.readUInt16();
  const initialUsbVoltage = reader.readUInt16();
  const initialAuxVoltage = reader.readUInt16();
  const captureDataMask = reader.readUInt16();
  const sampleCount = reader.readUInt64();
  const missingCount = reader.readUInt64();
  const count = Math.max(1, Number(sampleCount - missingCount));
  const avgMainVoltage = reader.readSingle() / count;
  const avgMainCurrent = reader.readSingle() / count;
  const avgMainPower = reader.readSingle() / count;
  const avgUsbVoltage = reader.readSingle() / count;
  const avgUsbCurrent = reader.readSingle() / count;
  const avgUsbPower = reader.readSingle() / count;
  const avgAuxVoltage = reader.readSingle() / count;
  const avgAuxCurrent = reader.readSingle() / count;
  const avgAuxPower = reader.readSingle() / count;
  return {
    headSize,
    name,
    batterySize,
    captureDate,
    serialNumber,
    calibrationStatus,
    voutSetting,
    voutValue,
    hardwareRate,
    softwareRate: hardwareRate,
    powerField,
    currentField,
    voltageField,
    captureSetting,
    swVersion,
    runMode,
    exitCode,
    totalCount,
    statusOffset,
    statusSize,
    sampleOffset,
    sampleSize,
    initialMainVoltage,
    initialUsbVoltage,
    initialAuxVoltage,
    captureDataMask,
    sampleCount,
    missingCount,
    avgMainVoltage,
    avgMainCurrent,
    avgMainPower,
    avgUsbVoltage,
    avgUsbCurrent,
    avgUsbPower,
    avgAuxVoltage,
    avgAuxCurrent,
    avgAuxPower,
  };
}

function parseStatusPacket(reader) {
  reader.pos = STATUS_OFFSET;
  reader.readByte();
  reader.readByte();
  reader.readByte();
  reader.readByte();
  reader.readInt16();
  reader.readInt16();
  reader.readInt16();
  reader.readUInt16();
  reader.readInt16();
  reader.readInt16();
  reader.readInt16();
  reader.readUInt16();
  reader.readByte();
  reader.readSByte();
  reader.readByte();
  reader.readByte();
  reader.readByte();
  reader.readSByte();
  reader.readUInt16();
  const sampleRate = reader.readByte();
  return { sampleRate };
}

function bytesPerSample(captureDataMask) {
  let result = 2;
  if ((captureDataMask & CHAN_MAIN) !== 0) result += 4;
  if ((captureDataMask & CHAN_USB) !== 0) result += 4;
  if ((captureDataMask & CHAN_AUX) !== 0) result += 4;
  return result;
}

function resolveSampleCount(header, buf, bps) {
  let sampleCount = Number(header.sampleCount);
  if (sampleCount <= 0) sampleCount = Number(header.totalCount);
  if (sampleCount <= 0) {
    sampleCount = Math.floor((buf.length - SAMPLE_OFFSET) / bps);
  }
  return Math.min(sampleCount, Math.floor((buf.length - SAMPLE_OFFSET) / bps));
}

/** TPowerMonitor 导出文件常见 sampleCount=0，需回退 totalCount / 文件长度。 */
function parseSamplesFallback(buf, header, sampleRateHz) {
  const bps = bytesPerSample(header.captureDataMask);
  const maxSamples = resolveSampleCount(header, buf, bps);
  const samples = [];
  for (let i = 0; i < maxSamples; i += 1) {
    let pos = SAMPLE_OFFSET + i * bps;
    const sample = {
      sampleIndex: i,
      timestampSec: i / sampleRateHz,
      missing: false,
      mainCurrentMA: 0,
      usbCurrentMA: 0,
      auxCurrentMA: 0,
    };
    if ((header.captureDataMask & CHAN_MAIN) !== 0) {
      const raw = buf.readInt32LE(pos);
      pos += 4;
      if (raw === MISSING_RAW_CURRENT_INT32) sample.missing = true;
      else sample.mainCurrentMA = raw / 1000.0;
    }
    if ((header.captureDataMask & CHAN_USB) !== 0) {
      const raw = buf.readInt32LE(pos);
      pos += 4;
      if (raw === MISSING_RAW_CURRENT_INT32) sample.missing = true;
      else sample.usbCurrentMA = raw / 1000.0;
    }
    if ((header.captureDataMask & CHAN_AUX) !== 0) {
      const raw = buf.readInt32LE(pos);
      pos += 4;
      if (raw === MISSING_RAW_CURRENT_INT32) sample.missing = true;
      else sample.auxCurrentMA = raw / 1000.0;
    }
    samples.push(sample);
  }
  return samples;
}

async function parsePt5Resolved(filePath) {
  const { parsePt5File } = await loadParser();
  const pt5 = parsePt5File(filePath);
  if (pt5.samples.length > 0) return pt5;
  const buf = fs.readFileSync(filePath);
  const samples = parseSamplesFallback(buf, pt5.header, pt5.sampleRateHz);
  return { ...pt5, samples };
}

function channelCurrent(sample, channel) {
  if (channel === "usb") return sample.usbCurrentMA;
  if (channel === "aux") return sample.auxCurrentMA;
  return sample.mainCurrentMA;
}

function extractCurrents(samples, channel = "main") {
  const out = [];
  for (const sample of samples) {
    if (sample.missing) continue;
    out.push(channelCurrent(sample, channel));
  }
  return out;
}

function resampleCurrent(currents, durationSec, rateHz) {
  if (!currents.length || durationSec <= 0) return [];
  const n = Math.max(1, Math.floor(durationSec * rateHz));
  if (currents.length <= n) return currents.slice();
  const chunk = currents.length / n;
  const out = new Array(n);
  for (let i = 0; i < n; i += 1) {
    const start = Math.floor(i * chunk);
    const end = Math.max(start + 1, Math.floor((i + 1) * chunk));
    let sum = 0;
    for (let j = start; j < end; j += 1) sum += currents[j];
    out[i] = sum / (end - start);
  }
  return out;
}

/** 按官方 getSample 字节序读取单点电流，避免构建全量 samples 数组。 */
function readChannelCurrentFromBuffer(buf, header, sampleIndex, channel) {
  const bps = bytesPerSample(header.captureDataMask);
  let offset = SAMPLE_OFFSET + sampleIndex * bps;
  if ((header.captureDataMask & CHAN_MAIN) !== 0) {
    const raw = buf.readInt32LE(offset);
    offset += 4;
    if (channel === "main") {
      if (raw === MISSING_RAW_CURRENT_INT32) return null;
      return raw / 1000.0;
    }
  }
  if ((header.captureDataMask & CHAN_USB) !== 0) {
    const raw = buf.readInt32LE(offset);
    offset += 4;
    if (channel === "usb") {
      if (raw === MISSING_RAW_CURRENT_INT32) return null;
      return raw / 1000.0;
    }
  }
  if ((header.captureDataMask & CHAN_AUX) !== 0) {
    const raw = buf.readInt32LE(offset);
    offset += 4;
    if (channel === "aux") {
      if (raw === MISSING_RAW_CURRENT_INT32) return null;
      return raw / 1000.0;
    }
  }
  return null;
}

/** 大文件流式重采样：只保留目标序列，不把原始采样全部载入堆。 */
function streamResampleFromBuffer(buf, header, sampleRateHz, durationSec, rateHz, channel) {
  const bps = bytesPerSample(header.captureDataMask);
  const maxSamples = resolveSampleCount(header, buf, bps);
  const effectiveDuration =
    durationSec > 0 ? durationSec : maxSamples / Math.max(sampleRateHz, 1);
  const outN = Math.max(1, Math.floor(effectiveDuration * rateHz));
  const out = new Array(outN);
  let rawValid = 0;
  let rawSum = 0;
  const chunk = maxSamples / outN;
  for (let i = 0; i < outN; i += 1) {
    const start = Math.floor(i * chunk);
    const end = Math.max(start + 1, Math.floor((i + 1) * chunk));
    let sum = 0;
    let cnt = 0;
    for (let j = start; j < end; j += 1) {
      const v = readChannelCurrentFromBuffer(buf, header, j, channel);
      if (v !== null) {
        sum += v;
        cnt += 1;
        rawValid += 1;
        rawSum += v;
      }
    }
    out[i] = cnt ? sum / cnt : 0;
  }
  return {
    series: out,
    raw_sample_count: rawValid,
    raw_mean_ma: rawValid ? rawSum / rawValid : null,
    native_sample_rate_hz: sampleRateHz,
    sample_rate_hz: durationSec > 0 ? rateHz : sampleRateHz,
  };
}

function parseArgs(argv) {
  const args = { _: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (token.startsWith("--")) {
      const key = token.slice(2).replace(/-/g, "_");
      const next = argv[i + 1];
      if (next && !next.startsWith("--")) {
        args[key] = next;
        i += 1;
      } else {
        args[key] = true;
      }
    } else {
      args._.push(token);
    }
  }
  return args;
}

async function cmdSeries(args) {
  const filePath = args.file || args._[1];
  if (!filePath) {
    throw new Error("缺少 --file <path>");
  }
  const durationSec = Number(args.duration_sec ?? args._[2] ?? 0);
  const rateHz = Number(args.rate_hz ?? 32);
  const channel = String(args.channel || "main");
  if (!fs.existsSync(filePath)) {
    throw new Error(`文件不存在: ${filePath}`);
  }
  const fileSize = fs.statSync(filePath).size;
  const useStreaming = durationSec > 0 || fileSize >= LARGE_FILE_BYTES;

  if (useStreaming) {
    const buf = fs.readFileSync(filePath);
    const meta = parsePt5MetaLight(buf);
    const streamed = streamResampleFromBuffer(
      buf,
      meta.header,
      meta.sampleRateHz,
      durationSec,
      rateHz,
      channel
    );
    const series = streamed.series;
    const mean = series.length ? series.reduce((a, b) => a + b, 0) / series.length : null;
    process.stdout.write(
      JSON.stringify({
        path: filePath,
        channel,
        native_sample_rate_hz: streamed.native_sample_rate_hz,
        raw_sample_count: streamed.raw_sample_count,
        point_count: series.length,
        raw_mean_ma: streamed.raw_mean_ma,
        mean_ma: mean,
        sample_rate_hz: streamed.sample_rate_hz,
        series,
        parser_mode: "stream-resample",
      })
    );
    return;
  }

  const pt5 = await parsePt5Resolved(filePath);
  const raw = extractCurrents(pt5.samples, channel);
  const series = durationSec > 0 ? resampleCurrent(raw, durationSec, rateHz) : raw;
  const rawMean = raw.length ? raw.reduce((a, b) => a + b, 0) / raw.length : null;
  const mean = series.length ? series.reduce((a, b) => a + b, 0) / series.length : null;
  process.stdout.write(
    JSON.stringify({
      path: filePath,
      channel,
      native_sample_rate_hz: pt5.sampleRateHz,
      raw_sample_count: raw.length,
      point_count: series.length,
      raw_mean_ma: rawMean,
      mean_ma: mean,
      sample_rate_hz: durationSec > 0 ? rateHz : pt5.sampleRateHz,
      series,
    })
  );
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const command = args._[0] || "series";
  if (command === "series") {
    await cmdSeries(args);
    return;
  }
  throw new Error(`未知子命令: ${command}（支持: series）`);
}

main().catch((err) => {
  process.stderr.write(`${err.message || err}\n`);
  process.exit(1);
});
