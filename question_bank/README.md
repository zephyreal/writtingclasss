# 学术论文写作短题库

本版共640道原创教学短题：八单元，每单元80题（56道三选一、24道判断）。
每单元八个知识点，每点十题。所有题干、情境、选项和解析为本项目编写，不复制来源练习题或原文句式。
资料用于核对通用写作原则，不表示来源机构认可本题库，也不表示题库适合所有学科或目标期刊。

## 编辑格式

`unit1.txt` 至 `unit8.txt` 是可读源文件。`# 知识点名`后恰好十行：
前七行单选，格式`题干|正确选项|干扰项一|干扰项二|解析`；后三行判断，格式`题干|T或F|解析`。
加载时单选答案位置轮换，发题时再次随机排列选项；判断固定为“正确/错误”。学生接口不提前发送答案、解析、题目难度或推荐知识点。
题号按单元/知识点/位置稳定生成。修改题目不会改写已完成记录中的题目与答案快照。

每知识点十题的编辑难度为`1,1,2,2,2,3,3,1,2,2`，每单元为基础24/应用40/比较判断16。
这些为编写标签，不是经过教学数据标定的难度或测量量表。十秒短题主要检查快速判断，不能替代独立写作、长材料分析或论文评价。
首批学生使用后应根据超时率、选项分布和教师反馈调整歧义题与干扰项，而不是将超时直接归因为不会。

## 参考资料与原则核对（2026-10-20）

以下为参考资料索引；题目包含自编应用与综合判断，并非对每页逐句改写。
具体题目对应的参考类别见`practice_bank.py`的SOURCE_MAP；作答完成后可展开查看资料链接。
不将通用原则冒充某一期刊的强制格式，遇到要求差异以课程与目标期刊现行规则为准。

- George Mason University, [How to Write a Research Question](https://writingcenter.gmu.edu/writing-resources/research-based-writing/how-to-write-a-research-question)：问题聚焦、清晰与可研究性。
- Purdue OWL, [Writing a Literature Review](https://owl.purdue.edu/owl/research_and_citation/conducting_research/writing_a_literature_review.html)：文献关系、主题组织与研究定位。
- George Mason University, [Writing a Literature Review](https://writingcenter.gmu.edu/writing-resources/research-based-writing/writing-a-literature-review)：从逐篇概括转向综合比较。
- Cornell University Library, [How to Search Scholarly Databases](https://guides.library.cornell.edu/public-health/how-to-search-for-resources)：AND/OR/NOT与数据库检索。
- George Mason University, [IMRaD: Results and Discussion](https://writingcenter.gmu.edu/writing-resources/imrad/imrad-results-discussion)：观测、解释与讨论功能。
- UNC Writing Center, [Abstracts](https://writingcenter.unc.edu/tips-and-tools/abstracts/)：摘要功能与核心研究信息。
- UNC Writing Center, [Figures and Charts](https://writingcenter.unc.edu/tips-and-tools/figures-and-charts/)：选择展示形式、图文联系与说明信息。
- UNC Writing Center, [Revising Drafts](https://writingcenter.unc.edu/tips-and-tools/revising-drafts/)：论点、证据与组织的实质修改，不止校对。
- PLOS One, [Submission Guidelines](https://journals.plos.org/plosone/s/submission-guidelines)：方法报告、材料、数据与研究透明性；其中期刊专属细则未作为全学科统一规则。
- scikit-learn, [Common pitfalls and recommended practices](https://scikit-learn.org/stable/common_pitfalls.html)：预处理数据泄漏、训练测试分离。
- Nature Methods, [Error bars](https://www.nature.com/articles/nmeth.2659)：误差条类型与含义区分。
- Nature Communications, [Reproducibility: let's get it right from the start](https://www.nature.com/articles/s41467-018-06012-8)：样本与变异报告。
- Purdue OWL, [Quoting, Paraphrasing, and Summarizing](https://owl.purdue.edu/owl/research_and_citation/using_research/quoting_paraphrasing_and_summarizing/index.html)：准确转述与来源归属。
- COPE, [Authorship and AI tools](https://doi.org/10.24318/cCVRZBms)：AI工具使用不转移作者责任（检索摘要已核对，官网全文本次不可访问）。

本题库不需要联网检索作答，不虚构真实论文、DOI、政策或实验数据；涉及数据的微情境均为自编教学设定。
不把题库训练正确率作为学术诚信判断，不声称已核实学生引用与原始数据真实性。

校验：`python -m pytest -q test_adaptive_practice.py`。
