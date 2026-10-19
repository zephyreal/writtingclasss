# AI五子棋案例来源

课程：智能制造课程设计。

源仓库：https://github.com/zephyreal/Gomoku-VCT-Web

导入提交：`ca48f0712a5238f18dd9596d6b521ba953ca2976`。

`gomoku/` 中的9个原始文件逐字节保留，包括正式入口index.html、ai-worker.js、两个ONNX模型、历史实验页面及C++/旧Worker源码。源仓库由本次用户明确要求集成，本次未改动源仓库。

平台实际开放的入口为 `/courses/design/gomoku/`，使用index.html → ai-worker.js → gomoku_uint8_qop_u8u8.onnx。所有这些资源都需要当前平台登录。模型与Worker从本服务器加载，不是跳转到GitHub Pages。

原项目的ONNX Runtime Web 1.18.0仍由jsDelivr CDN加载。首次体验需要浏览器能访问该运行库；本次未把运行库WASM打包到服务器，也未做完整浏览器对弈验收。正式入口使用单线程WASM。历史vct-worker.js引用的gomoku-engine.wasm不在原仓库，本次未补造该文件，正式入口也不使用该旧Worker。历史实验页面仅作为源项目存档保留，不作为课程主入口。

平台将对弈作为交互学习案例；原项目的本地难度、声音设置继续有效。当前未接入对弈成绩、棋谱或服务器学习记录，不与论文写作的成绩混用。
