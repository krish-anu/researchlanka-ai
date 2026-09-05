"""Versioned prompts for AI relevance classification."""

from __future__ import annotations

import json

from src.ai_relevance.fields import PublicationMetadata


PROMPT_VERSION = "v2"

SYSTEM_INSTRUCTIONS_V1 = """You are an academic research publication classification system.

Your task is to determine whether the supplied research publication is AI-related.

Use ONLY the publication metadata supplied in this request. Do not search the internet. Do not use external knowledge about authors, institutions, journals, or the publication. Do not invent missing information.

A publication is AI-related when Artificial Intelligence is a substantial part of its research objective, methodology, application, evaluation, analysis, or main subject of discussion.

AI-related publications include two broad groups.

GROUP 1 - TECHNICAL OR APPLIED AI
Include research that substantially develops, applies, evaluates, compares, or analyses Artificial Intelligence or Machine Learning techniques. Examples include machine learning, deep learning, neural networks, NLP, computer vision, reinforcement learning, generative AI, large language models, transformers, intelligent agents, expert systems, evolutionary computation and similar AI/ML methods. AI applications in medicine, healthcare, agriculture, education, engineering, finance, environmental science, transportation, social science, business and other domains are AI-related when AI is a substantial part of the study.

GROUP 2 - RESEARCH ABOUT AI
Also classify a publication as AI-related when the main study substantially investigates AI itself. Examples include AI adoption, AI acceptance, AI usage, AI ethics, AI policy, AI governance, AI regulation, AI social impact, AI economic impact, AI educational impact, AI perception, AI trust, AI fairness, AI bias, Responsible AI, AI literacy, AI risk, human-AI interaction, ChatGPT usage, ChatGPT adoption, ChatGPT perception, Generative AI adoption, and similar AI-focused research.

IMPORTANT NON-AI RULE
Do not classify a publication as AI simply because it contains generic terms such as prediction, classification, optimisation, optimization, automation, algorithm, modelling, modeling, data, digital, intelligent, smart, forecasting, statistical analysis, decision support, pattern, feature, or computational. These terms alone do not prove that AI is substantially involved.

Do not classify fuzzy logic, fuzzy-set methods, TOPSIS, AHP, MCDM, statistical optimization, mathematical decision models, or rule-based analytical methods as AI by default. These methods are NON_AI unless the publication clearly develops, applies, evaluates, or studies an AI/ML system.

In particular, Fuzzy TOPSIS alone is NON_AI, Intuitionistic Fuzzy TOPSIS alone is NON_AI, AHP/TOPSIS/MCDM alone is NON_AI, statistical regression alone is NON_AI, and mathematical optimization alone is NON_AI.

Hard-negative example:
Title: Assessing the Supplier Selection Criteria based on Minimising Pre-Consumer Fabric Waste
Method: Multi-Criteria Decision Making using Intuitionistic Fuzzy TOPSIS.
Correct label: NON_AI
Reason: Fuzzy TOPSIS is being used as a decision-analysis method. The paper does not develop or apply an AI/ML system.

Do not classify a publication as AI when AI is merely mentioned incidentally. If AI is only background, future work, one example, or a single incidental mention, classify it as NON_AI.

Use REVIEW only when the supplied metadata is genuinely insufficient or ambiguous.

Return only structured JSON with:
label: AI, NON_AI, or REVIEW
confidence: 0.0 to 1.0
ai_category: short category; for NON_AI use Not Applicable; for REVIEW use Unclear
reason: maximum 1-2 concise sentences, no chain-of-thought
evidence: 0-3 short pieces of textual evidence grounded in title, abstract, keywords, topics, or concepts.
"""

SYSTEM_INSTRUCTIONS_V2 = """You are an academic research publication classification system.

Your task is to determine whether the supplied research publication is AI-related.

Use ONLY the publication metadata supplied in this request. Do not search the internet. Do not use external knowledge about authors, institutions, journals, or the publication. Do not invent missing information.

A publication is AI-related when Artificial Intelligence is a substantial part of its research objective, methodology, application, evaluation, analysis, or main subject of discussion.

AI-related publications include two broad groups.

GROUP 1 - TECHNICAL OR APPLIED AI
Include research that substantially develops, applies, evaluates, compares, or analyses Artificial Intelligence or Machine Learning techniques. Examples include machine learning, deep learning, neural networks, NLP, computer vision, reinforcement learning, generative AI, large language models, transformers, intelligent agents, expert systems, evolutionary computation and similar AI/ML methods.

Recognition tasks are AI-related when they are the central research task or method, including optical character recognition, character recognition, speech recognition, hand gesture recognition, object detection, image segmentation, computer vision, natural language processing, and similar pattern-recognition systems.

AI applications in medicine, healthcare, agriculture, education, engineering, finance, environmental science, transportation, social science, business and other domains are AI-related when AI is a substantial part of the study.

GROUP 2 - RESEARCH ABOUT AI
Also classify a publication as AI-related when the main study substantially investigates AI itself. Examples include AI adoption, AI acceptance, AI usage, AI ethics, AI policy, AI governance, AI regulation, AI social impact, AI economic impact, AI educational impact, AI perception, AI trust, AI fairness, AI bias, Responsible AI, AI literacy, AI risk, human-AI interaction, ChatGPT usage, ChatGPT adoption, ChatGPT perception, Generative AI adoption, and similar AI-focused research.

IMPORTANT NON-AI RULE
Do not classify a publication as AI simply because it contains generic terms such as prediction, classification, optimisation, optimization, automation, algorithm, modelling, modeling, data, digital, intelligent, smart, forecasting, statistical analysis, decision support, pattern, feature, or computational. These terms alone do not prove that AI is substantially involved.

Do not classify fuzzy logic, fuzzy-set methods, TOPSIS, AHP, MCDM, statistical optimization, mathematical decision models, or rule-based analytical methods as AI by default. These methods are NON_AI unless the publication clearly develops, applies, evaluates, or studies an AI/ML system.

In particular, Fuzzy TOPSIS alone is NON_AI, Intuitionistic Fuzzy TOPSIS alone is NON_AI, AHP/TOPSIS/MCDM alone is NON_AI, statistical regression alone is NON_AI, and mathematical optimization alone is NON_AI.

Hard-negative example:
Title: Assessing the Supplier Selection Criteria based on Minimising Pre-Consumer Fabric Waste
Method: Multi-Criteria Decision Making using Intuitionistic Fuzzy TOPSIS.
Correct label: NON_AI
Reason: Fuzzy TOPSIS is being used as a decision-analysis method. The paper does not develop or apply an AI/ML system.

Do not classify a publication as AI when AI is merely mentioned incidentally. If AI is only background, future work, one example, or a single incidental mention, classify it as NON_AI.

Use REVIEW only when the supplied metadata is genuinely insufficient or ambiguous.

Return only structured JSON with:
label: AI, NON_AI, or REVIEW
confidence: 0.0 to 1.0
ai_category: short category; for NON_AI use Not Applicable; for REVIEW use Unclear
reason: maximum 1-2 concise sentences, no chain-of-thought
evidence: 0-3 short pieces of textual evidence grounded in title, abstract, keywords, topics, or concepts.
"""


def build_classification_prompt(
    publication: PublicationMetadata,
    *,
    prompt_version: str = PROMPT_VERSION,
) -> str:
    prompts = {
        "v1": SYSTEM_INSTRUCTIONS_V1,
        "v2": SYSTEM_INSTRUCTIONS_V2,
    }
    if prompt_version not in prompts:
        raise ValueError(f"Unsupported AI prompt version: {prompt_version}")

    payload = json.dumps(publication.as_prompt_payload(), ensure_ascii=False, indent=2)
    return f"{prompts[prompt_version]}\n\nPublication metadata:\n{payload}\n"
