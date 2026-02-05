from reportlab.lib.pagesizes import LETTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib import colors
from reportlab.lib.units import inch

def create_resume():
    # File name
    pdf_filename = "Nurmukhamed_AI_Engineer_Resume.pdf"
    
    # Document Setup
    doc = SimpleDocTemplate(
        pdf_filename, 
        pagesize=LETTER,
        topMargin=0.5*inch, 
        bottomMargin=0.5*inch, 
        leftMargin=0.5*inch, 
        rightMargin=0.5*inch
    )

    styles = getSampleStyleSheet()
    story = []

    # --- Custom Styles ---
    # Header Name
    style_name = ParagraphStyle(
        name='Name', 
        parent=styles['Heading1'], 
        alignment=TA_CENTER, 
        fontSize=20, 
        spaceAfter=4,
        fontName='Helvetica-Bold'
    )
    # Role/Title
    style_role = ParagraphStyle(
        name='Role', 
        parent=styles['Normal'], 
        alignment=TA_CENTER, 
        fontSize=12, 
        spaceAfter=2,
        fontName='Helvetica-Bold'
    )
    # Contact Info
    style_contact = ParagraphStyle(
        name='Contact', 
        parent=styles['Normal'], 
        alignment=TA_CENTER, 
        fontSize=10, 
        textColor=colors.darkgray
    )
    # Section Headers (Lines under text)
    style_section = ParagraphStyle(
        name='SectionHeader', 
        parent=styles['Heading2'], 
        fontSize=12, 
        spaceBefore=12, 
        spaceAfter=6, 
        borderPadding=2, 
        borderWidth=0, 
        borderBottomWidth=1,
        borderColor=colors.black,
        fontName='Helvetica-Bold',
        textTransform='uppercase'
    )
    # Normal Text
    style_normal = ParagraphStyle(
        name='NormalText', 
        parent=styles['Normal'], 
        fontSize=10, 
        leading=14
    )
    # Project Title line
    style_proj_title = ParagraphStyle(
        name='ProjectTitle', 
        parent=styles['Normal'], 
        fontSize=10.5, 
        spaceBefore=6, 
        spaceAfter=2,
        fontName='Helvetica-Bold'
    )
    # Bullet points (using indent)
    style_bullet = ParagraphStyle(
        name='BulletPoint', 
        parent=styles['Normal'], 
        fontSize=10, 
        leading=14,
        leftIndent=12,
        firstLineIndent=0
    )

    # --- Content Data ---

    # 1. Header
    story.append(Paragraph("Nurmukhamed Ashekey", style_name))
    story.append(Paragraph("AI Engineer", style_role))
    story.append(Paragraph("Almaty, Kazakhstan | github.com/nurmukhamedkz | linkedin.com/in/nurmukhamed-ashekey-3031a3369", style_contact))
    story.append(Spacer(1, 10))

    # 2. Professional Summary
    story.append(Paragraph("PROFESSIONAL SUMMARY", style_section))
    summary_text = ("AI Engineer with robust experience in AI applications development, ranging from architecting "
                    "Retrieval-Augmented Generation (RAG) systems to deploying Computer Vision models in production. "
                    "Proficient in PyTorch, with a strong focus on building scalable backend services and LLM applications "
                    "using FastAPI and Docker. Skilled in optimization techniques for LLMs and developing end-to-end "
                    "machine learning pipelines that solve complex classification and retrieval problems.")
    story.append(Paragraph(summary_text, style_normal))

    # 3. Technical Skills
    story.append(Paragraph("TECHNICAL SKILLS", style_section))
    skills = [
        "<b>Machine Learning:</b> Pandas, Numpy, Scikit-Learn, Scipy, seaborn, matplotlib",
        "<b>Deep Learning:</b> PyTorch, TensorFlow/Keras, CNNs, Hugging Face Transformers, LLMs (Gemini, Llama 3).",
        "<b>Generative AI:</b> RAG Architectures, LangChain, Vector Databases (Qdrant), Embeddings.",
        "<b>Backend & MLOps:</b> Python, FastAPI, Docker, REST APIs, Redis, ONNX Runtime.",
        "<b>Computer Vision:</b> Grad-CAM, Image Classification, OpenCV."
    ]
    for skill in skills:
        story.append(Paragraph(skill, style_normal))

    # 4. Projects
    story.append(Paragraph("PROJECTS", style_section))
    
    # Project 1
    story.append(Paragraph("JauapAI – Enterprise RAG System | <font color='gray'>Python, FastAPI, LangChain, Qdrant, React</font>", style_proj_title))
    p1_points = [
        "Users required precise, context-aware answers extracted from massive, unstructured academic datasets where traditional search failed.",
        "Architect and deploy a scalable RAG engine to index and query textbook content in real-time.",
        "Engineered a high-performance backend using FastAPI. Implemented a Hybrid Search strategy in Qdrant, combining dense embeddings (VoyageAI) with sparse vectors (BGE-M3) for maximum retrieval accuracy. Integrated LlamaParse for complex PDF ingestion and Gemini 3 flash for reasoning.",
        "Deployed a production-ready MVP that reduced information retrieval time by 90%, delivering grounded answers with high semantic accuracy."
    ]
    for p in p1_points:
        story.append(Paragraph(f"• {p}", style_bullet))

    # Project 2
    story.append(Paragraph("Lung Disease Classification System | <font color='gray'>Python, TensorFlow/Keras, FastAPI, JavaScript</font>", style_proj_title))
    p2_points = [
        "Automated analysis of X-ray imagery required a robust, deployable solution to assist in rapid pathology detection.",
        "Build an end-to-end Computer Vision web application capable of classifying chest X-rays with high sensitivity.",
        "Trained a custom Convolutional Neural Network (CNN) on the Tuberculosis Chest X-ray dataset using TensorFlow/Keras. Developed a FastAPI microservice to serve model predictions and built a responsive frontend interface. Implemented Grad-CAM (Gradient-weighted Class Activation Mapping) to visualize model attention and improve explainability.",
        "Successfully deployed a model achieving high recall and precision, providing users with instant visual feedback and confidence scores."
    ]
    for p in p2_points:
        story.append(Paragraph(f"• {p}", style_bullet))

    # Project 3
    story.append(Paragraph("MakeMore – LLM Architecture Implementation | <font color='gray'>Python, PyTorch, Deep Learning</font>", style_proj_title))
    p3_points = [
        "Mastering the optimization of Large Language Models requires a first-principles understanding of matrix operations and gradients.",
        "Build and train autoregressive language models from scratch without high-level abstractions.",
        "Implemented complex neural architectures including Multi-Layer Perceptrons (MLP), WaveNet, and Decoder-only Transformers. Manually coded Backpropagation, Batch Normalization, and Self-Attention layers to benchmark performance against standard implementations.",
        "Created convergent models capable of generating coherent text sequences, demonstrating deep technical mastery of Transformer internals."
    ]
    for p in p3_points:
        story.append(Paragraph(f"• {p}", style_bullet))

    # Project 4
    story.append(Paragraph("NLP for Transformers – Model Optimization Pipeline | <font color='gray'>Python, Hugging Face, ONNX</font>", style_proj_title))
    p4_points = [
        "Deploying NLP tasks like Named Entity Recognition (NER) in resource-constrained environments required optimized inference.",
        "Fine-tune and compress pre-trained Transformer models for production use.",
        "Fine-tuned BERT-based models on custom datasets. Applied Model Quantization and exported models to ONNX format to minimize latency and memory usage.",
        "Delivered task-specific models that maintained high accuracy while significantly reducing computational overhead."
    ]
    for p in p4_points:
        story.append(Paragraph(f"• {p}", style_bullet))

    # 5. Education
    story.append(Paragraph("EDUCATION", style_section))
    story.append(Paragraph("Bachelor of Computer Science, KBTU", style_normal))
    story.append(Paragraph("Self-Study via Books and projects", style_normal))

    # Build PDFZ
    doc.build(story)
    print(f"PDF created successfully: {pdf_filename}")

if __name__ == "__main__":
    create_resume()