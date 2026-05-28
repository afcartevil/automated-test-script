# Phase 2 实现计划：向量搜索 + 文档导入工具

**目标**: 升级知识库系统，支持向量相似度搜索和多格式文档自动导入  
**时间估计**: 2-3 周  
**优先级**: 高

---

## 1. 向量搜索集成（ChromaDB）

### 1.1 后端架构

```
tahp-mcp-server/
├── handlers/
│   └── knowledge_vector.py          (新建：向量搜索处理器)
│
├── services/
│   └── vector_store.py              (新建：ChromaDB 包装)
│
└── requirements.txt                 (更新：添加依赖)
```

### 1.2 Python 依赖

```
chromadb==0.5.0
sentence-transformers==2.2.2
torch==2.0.0  (或 torch-cpu for minimal setup)
```

### 1.3 向量存储设计

**VectorStore 类** (tahp-mcp-server/services/vector_store.py):
```python
class VectorStore:
    def __init__(self, persist_dir: str):
        """初始化 ChromaDB，指定持久化目录"""
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = None
        self.embedding_model = None
    
    async def initialize(self):
        """启动时初始化向量模型和集合"""
        # 加载中文多语言嵌入模型
        self.embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        self.collection = self.client.get_or_create_collection(
            name='knowledge_entries',
            metadata={'hnsw:space': 'cosine'}
        )
    
    async def add_entry(self, entry_id: str, content: str, metadata: dict):
        """添加知识条目到向量库"""
        embedding = self.embedding_model.encode(content).tolist()
        self.collection.add(
            ids=[entry_id],
            embeddings=[embedding],
            metadatas=[metadata],
            documents=[content]
        )
    
    async def search(self, query: str, top_k: int = 5, min_confidence: float = 0.6):
        """向量搜索"""
        query_embedding = self.embedding_model.encode(query).tolist()
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )
        # 过滤和格式化结果
        return self._format_results(results, min_confidence)
    
    async def delete_entry(self, entry_id: str):
        """删除条目"""
        self.collection.delete(ids=[entry_id])
    
    async def update_entry(self, entry_id: str, content: str, metadata: dict):
        """更新条目"""
        await self.delete_entry(entry_id)
        await self.add_entry(entry_id, content, metadata)
```

### 1.4 新增 API 端点

修改 `/api/tahp/knowledge/search/semantic`:
```python
# tahp-console/packages/server/src/routes/tahp/knowledge.ts

tahpKnowledgeRoutes.post('/api/tahp/knowledge/search/semantic', async (ctx) => {
  // 调用 MCP 工具：knowledge_vector_search
  const results = await getMcpBridge().callTool('knowledge_vector_search', {
    query: body.query,
    module: body.module,
    top_k: body.top_k || 5,
    min_confidence: body.min_confidence || 0.6
  })
  ctx.body = { success: true, data: results }
})
```

### 1.5 与现有知识库的集成

- 当创建知识条目时，自动添加到向量库
- 当更新知识条目时，更新向量库
- 当删除知识条目时，从向量库移除
- 搜索时：优先返回向量相似度高的结果

---

## 2. 文档导入工具

### 2.1 后端架构

```
tahp-mcp-server/
├── handlers/
│   └── document_ingestion.py        (新建：文档摄入处理器)
│
├── services/
│   ├── document_parser.py           (新建：多格式解析器)
│   └── text_chunker.py              (新建：文本分块器)
│
└── requirements.txt                 (更新：添加 unstructured 等)
```

### 2.2 Python 依赖

```
unstructured==0.14.0
pdf2image==1.16.0
pytesseract==0.3.10
python-docx==0.8.11
openpyxl==3.1.2
pptx==0.1.0
pillow==10.0.0
```

### 2.3 文档处理流程

```
上传文件 → 格式检测 → 内容提取 → 文本分块 → 知识条目生成 → 向量化 → 存储
```

**DocumentParser 类** (tahp-mcp-server/services/document_parser.py):
```python
class DocumentParser:
    """多格式文档解析器"""
    
    @staticmethod
    async def parse_pdf(file_path: str) -> List[DocumentChunk]:
        """解析 PDF"""
        elements = partition_pdf(file_path)
        return [DocumentChunk(text=str(el), metadata={'type': 'pdf'}) for el in elements]
    
    @staticmethod
    async def parse_docx(file_path: str) -> List[DocumentChunk]:
        """解析 Word"""
        doc = Document(file_path)
        chunks = []
        for para in doc.paragraphs:
            if para.text.strip():
                chunks.append(DocumentChunk(text=para.text, metadata={'type': 'docx'}))
        return chunks
    
    @staticmethod
    async def parse_excel(file_path: str) -> List[DocumentChunk]:
        """解析 Excel"""
        wb = load_workbook(file_path)
        chunks = []
        for sheet in wb.sheetnames:
            ws = wb[sheet]
            for row in ws.iter_rows(values_only=True):
                if any(row):
                    chunks.append(DocumentChunk(
                        text=' | '.join(str(c) for c in row if c),
                        metadata={'type': 'excel', 'sheet': sheet}
                    ))
        return chunks
    
    @staticmethod
    async def parse_markdown(file_path: str) -> List[DocumentChunk]:
        """解析 Markdown"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        # 按标题分块
        chunks = []
        sections = re.split(r'#{1,3}\s+', content)
        for section in sections:
            if section.strip():
                chunks.append(DocumentChunk(text=section.strip(), metadata={'type': 'markdown'}))
        return chunks
```

**TextChunker 类** (tahp-mcp-server/services/text_chunker.py):
```python
class TextChunker:
    """文本分块器"""
    
    @staticmethod
    def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> List[str]:
        """
        将长文本分块
        - chunk_size: 每块的字符数
        - overlap: 相邻块的重叠字符数
        """
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end])
            start = end - overlap
        return chunks
    
    @staticmethod
    def extract_metadata(chunk: str, source_file: str) -> dict:
        """从 chunk 提取元数据"""
        # 提取第一句作为摘要
        sentences = re.split(r'[。！？\n]', chunk)
        first_sentence = sentences[0] if sentences else chunk[:50]
        
        return {
            'source_file': source_file,
            'summary': first_sentence[:100],
            'length': len(chunk),
        }
```

### 2.4 新增 API 端点

**POST /api/tahp/knowledge/ingest** (tahp-console/packages/server/src/routes/tahp/knowledge.ts):
```typescript
tahpKnowledgeRoutes.post('/api/tahp/knowledge/ingest', async (ctx) => {
  // 接收文件上传
  const files = ctx.request.files
  const { module, func_type } = ctx.request.body
  
  // 调用 MCP 工具：document_ingest
  const result = await getMcpBridge().callTool('document_ingest', {
    file_paths: files.map(f => f.filepath),
    module,
    func_type,
  })
  
  ctx.body = { success: true, data: result }
})

// GET /api/tahp/knowledge/ingest/:ingestionId/progress (实时进度)
tahpKnowledgeRoutes.get('/api/tahp/knowledge/ingest/:ingestionId/progress', async (ctx) => {
  // 查询摄入任务进度
})
```

### 2.5 摄入流程

1. 用户上传文件
2. 后端验证文件类型和大小
3. 异步启动文档处理任务
4. 前端轮询获取进度
5. 处理完成后自动创建知识条目
6. 向量库自动索引

---

## 3. 前端支持

### 3.1 文件上传组件 (DocumentIngestionWidget.vue)

```typescript
// 功能需求：
- 文件拖拽上传
- 支持多文件选择
- 文件类型过滤（PDF、DOCX、XLSX、PPTX、MD）
- 上传进度显示
- 处理进度实时更新
- 完成后显示摄入结果（创建的条目数、错误数）
```

### 3.2 搜索结果展示优化

在 KnowledgeManagementView.vue 中：
- 语义搜索结果加入"相似度评分"
- 结果排序：优先显示相似度高的
- 结果摘要：高亮相关部分

---

## 4. 实现顺序

### Step 1: 向量搜索基础 (2 天)
- [ ] 集成 ChromaDB 和 sentence-transformers
- [ ] 实现 VectorStore 类
- [ ] 创建 knowledge_vector_search MCP 工具
- [ ] 在知识库管理中测试向量搜索

### Step 2: 文档导入基础 (3 天)
- [ ] 集成 Unstructured 和相关库
- [ ] 实现 DocumentParser 和 TextChunker
- [ ] 创建 document_ingest MCP 工具
- [ ] 前端上传界面

### Step 3: 集成与优化 (2 天)
- [ ] CRUD 操作与向量库同步
- [ ] 异步处理和实时进度通知
- [ ] 搜索结果排序和展示优化
- [ ] 性能测试和调优

### Step 4: 测试与文档 (1 天)
- [ ] 端到端集成测试
- [ ] 使用文档
- [ ] 性能基准测试

---

## 5. 部署检查清单

- [ ] Python 环境：Python 3.10+
- [ ] 新依赖已安装：`pip install -r requirements.txt`
- [ ] ChromaDB 持久化目录已创建
- [ ] 向量模型已下载缓存
- [ ] 前端 UI 已更新
- [ ] API 端点已验证
- [ ] 性能基准达标

---

## 6. 性能目标

| 操作 | 目标 | 说明 |
|------|------|------|
| 向量搜索 (10条) | < 100ms | 单条查询 |
| 向量搜索 (1000条) | < 500ms | 在索引建立后 |
| 文档解析 (PDF 5MB) | < 2s | 单文件 |
| 向量化 (1000条) | < 30s | 批量导入 |

---

## 7. 已知风险与缓解

| 风险 | 影响 | 缓解方案 |
|------|------|---------|
| 向量模型加载缓慢 | 启动时间延长 | 缓存、后台加载 |
| 大文件解析失败 | 摄入中断 | 文件大小限制、错误恢复 |
| 向量搜索返回不相关结果 | 用户体验差 | 调整阈值、混合搜索 |
| ChromaDB 磁盘占用过大 | 存储成本 | 定期清理、分片存储 |

---

**预计完成日期**: 1-2 周  
**Next Phase**: Phase 3 - 过期提醒 + 知识修改历史
