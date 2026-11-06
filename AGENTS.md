# AGENTS.md — MemoCard AI

## 1. Project Overview

### Project Name
MemoCard AI — An AI-Assisted Personalized Learning System

### Project Description

MemoCard AI is a web-based AI-assisted learning platform designed to help university students transform their study materials into structured learning resources and improve long-term knowledge retention.

The system integrates Retrieval-Augmented Generation (RAG), Large Language Models (LLMs), automated flashcard generation, and the SM-2 Spaced Repetition Algorithm.

Unlike general-purpose AI chatbots that primarily provide one-time answers, MemoCard AI aims to create a continuous learning workflow:

1. Students upload their study materials.
2. AI retrieves relevant information from uploaded documents.
3. Students ask questions and receive answers with source citations.
4. Students convert useful AI responses into flashcards.
5. The system schedules flashcard reviews using the SM-2 algorithm.
6. Students review their flashcards according to their revision schedule.

### Main Objectives

- Provide document-based AI question answering with source citations.
- Reduce the manual effort required to create flashcards.
- Improve long-term knowledge retention through spaced repetition.
- Provide a unified learning environment for managing study materials and revision activities.

---

## 2. Technology Stack

The following technologies define the project's current technical direction.

| Component | Technology | Purpose |
|---|---|---|
| Frontend | React | User interface and web application |
| Backend | Python + FastAPI | REST API and backend business logic |
| Relational Database | PostgreSQL | Store users, documents, flashcards and revision records |
| Vector Database | ChromaDB | Store document embeddings and perform semantic retrieval |
| LLM Provider | DeepSeek API | AI question answering and flashcard generation |
| AI Architecture | RAG | Ground AI responses in uploaded study materials |
| Revision Algorithm | SM-2 | Calculate flashcard review intervals |

### Technology Rules

- Use React for frontend development.
- Use FastAPI for backend API development.
- Use PostgreSQL as the primary relational database.
- Use ChromaDB for vector storage and semantic retrieval.
- Use DeepSeek API for LLM-related operations.
- Keep AI model integration separate from business logic where practical.
- Do not introduce additional frameworks, libraries, databases or external services without discussing their necessity with the developer first.

### Dependency Management

Before installing any new package:

1. Explain why the dependency is needed.
2. Explain what functionality it provides.
3. Check whether the existing technology stack can achieve the same purpose.
4. Wait for developer approval before installation.

Do not invent package versions. Check the existing project configuration before making dependency decisions.

---

## 3. Core Requirements and MVP Scope

The first development phase must focus on a functional Minimum Viable Product (MVP).

Do not attempt to implement every possible feature at once.

### 3.1 MVP Features

#### Module 1: User Authentication

- User registration.
- User login and logout.
- Basic user profile management.
- Protect user-specific data.

#### Module 2: Document Management

- Upload supported study documents.
- Initial supported formats: PDF, TXT and PPT.
- Store document metadata in PostgreSQL.
- Extract document text.
- Generate embeddings.
- Store embeddings in ChromaDB.
- Associate uploaded documents with their respective users.

#### Module 3: AI Chat with RAG

- Allow users to ask questions about uploaded study materials.
- Retrieve relevant document chunks using semantic search.
- Use retrieved context when generating answers through DeepSeek API.
- Display source citations alongside AI answers.
- Avoid presenting unsupported information as verified document content.
- Maintain chat history.

#### Module 4: Flashcard Generation

- Generate flashcards from AI chat responses.
- Support question-and-answer flashcard formats.
- Allow users to review and edit generated flashcards.
- Save flashcards in PostgreSQL.
- Associate flashcards with their respective users and source documents where available.

#### Module 5: Spaced Repetition System (SM-2)

- Implement the SM-2 spaced repetition algorithm.
- Track flashcard review performance.
- Calculate the next review date.
- Update repetition intervals based on user feedback.
- Store revision progress in PostgreSQL.

#### Module 6: Revision Calendar

- Display scheduled flashcard reviews.
- Show flashcards due today.
- Show upcoming revision tasks.
- Allow users to access their scheduled revision activities.

### 3.2 Additional Features — After MVP

These features are part of the broader project scope but should not take priority over the core MVP.

- Text-to-Speech for flashcards.
- Flashcard tagging and filtering.
- More advanced chat history management.
- Additional document processing improvements.

Only begin these features after the core MVP is functional and approved by the developer.

### 3.3 Out of Scope

The following features are explicitly excluded from the current project:

- Native Android or iOS mobile applications.
- Social networking features.
- Collaborative group studying.
- Real-time multiplayer learning.
- Official academic accreditation or degree certification.
- Training a custom Large Language Model from scratch.

The application will be developed as a responsive web application.

---

## 4. System Architecture Guidelines

The application should maintain a clear separation of responsibilities.

### Frontend

Responsible for:

- User interface.
- Authentication screens.
- Document upload interface.
- AI chat interface.
- Flashcard management.
- Revision calendar.
- Communication with backend APIs.

### Backend

Responsible for:

- Authentication and authorization.
- Document processing.
- Text extraction and chunking.
- Embedding generation.
- RAG retrieval pipeline.
- DeepSeek API integration.
- Flashcard generation.
- SM-2 calculations.
- Revision scheduling.
- Database operations.

### PostgreSQL

Responsible for storing structured relational data, including:

- User accounts.
- Document metadata.
- Chat sessions and messages.
- Flashcards.
- Flashcard review records.
- Revision schedules.

### ChromaDB

Responsible for:

- Storing document embeddings.
- Semantic similarity searches.
- Retrieving relevant document chunks for RAG.

### AI Processing Workflow

Document Upload → Text Extraction → Chunking → Embedding Generation → ChromaDB Storage → Semantic Retrieval → DeepSeek API → AI Response with Citations.

---

## 5. Codex Working Discipline (MANDATORY)

These rules are mandatory. Follow them throughout the entire development process.

### Rule 1: Read AGENTS.md First

Before starting any coding task:

- Read this AGENTS.md file.
- Understand the project objectives.
- Understand the technical stack.
- Understand the current MVP scope.
- Follow all development restrictions.

Never start coding without first understanding this document.

### Rule 2: One Independent Module at a Time

Do not implement the entire application in one operation.

Development must be divided into small, independent modules.

For example:

- Authentication Module.
- Database Module.
- Document Upload Module.
- Document Processing Module.
- RAG Module.
- AI Chat Module.
- Flashcard Module.
- SM-2 Algorithm Module.
- Revision Calendar Module.

Complete and verify one module before moving to the next.

Do not modify unrelated modules unless explicitly approved.

### Rule 3: Discuss Before Coding

This is one of the most important rules.

Before writing or modifying any code, you MUST:

1. Understand the requested feature.
2. Explain the proposed implementation in natural language.
3. Explain the expected workflow.
4. Identify which existing files or modules need to be created or modified.
5. Discuss the database changes, including tables, columns and relationships, if applicable.
6. Explain how the frontend, backend and database will interact.
7. Identify potential technical risks.

Then STOP and wait for explicit approval from the developer.

Do not generate code until the developer agrees with the implementation plan.

Silence or an ambiguous response does not count as approval.

### Rule 4: Database Design Before Implementation

Before implementing database-related features:

- Discuss the required tables.
- Identify primary keys and foreign keys.
- Define relationships between tables.
- Explain important columns and data types.
- Consider data integrity and user data isolation.
- Explain how the new tables interact with existing tables.

For major database changes, present the proposed schema or ERD in text or Mermaid format.

Wait for developer approval before implementing the database changes.

Never silently modify the existing database structure.

### Rule 5: Code Quality and Comments

All generated code must:

- Be readable and maintainable.
- Follow appropriate naming conventions.
- Use modular architecture.
- Avoid unnecessary duplication.
- Handle errors properly.
- Include meaningful comments explaining important implementation decisions.

Comments should explain WHY a particular approach is used, not simply repeat WHAT the code does.

Avoid excessive or meaningless comments.

### Rule 6: Respect Existing Project Files

Before modifying existing files:

- Inspect the current project structure.
- Read relevant source files.
- Understand existing implementation.
- Avoid overwriting working functionality.
- Preserve existing configurations unless changes are necessary and approved.

Never assume that a file or module does not exist without checking.

### Rule 7: Testing and Verification

After completing an approved module:

1. Explain what was implemented.
2. List the files created or modified.
3. Explain how to run or test the module.
4. Execute relevant tests where possible.
5. Report errors and incomplete functionality honestly.
6. Wait for approval before proceeding to another module.

Never claim that something works without verification.

### Rule 8: No Unauthorized Scope Expansion

Do not independently:

- Add unrequested features.
- Replace the selected technology stack.
- Introduce unnecessary dependencies.
- Change the project architecture.
- Rewrite large portions of the application.
- Implement future-phase features without permission.

If a better technical approach is identified, explain it and discuss it with the developer first.

### Rule 9: Skills and MCP Tools

For project design and development work, Codex may independently discover, add, configure, and use relevant Skills or MCP tools without requesting separate approval. This authorization covers tools used to assist development and does not change the project technology stack or waive the existing requirement to discuss runtime dependencies, frameworks, databases, or external services before introducing them into the application.

---

## 6. Development Workflow

Follow this workflow for every new development task:

**Phase 1 — Understand**

Read AGENTS.md and inspect the relevant existing project files.

**Phase 2 — Analyze**

Understand the requirements and identify dependencies.

**Phase 3 — Propose**

Present the implementation plan, database changes and affected files.

**Phase 4 — Wait for Approval**

Stop and wait for explicit developer approval.

**Phase 5 — Implement**

Implement only the approved independent module.

**Phase 6 — Verify**

Test the implementation and report the results.

**Phase 7 — Review**

Summarize completed work and request approval before starting the next module.

---

## 7. Communication Rules

When discussing technical decisions:

- Use clear and understandable language.
- Explain technical concepts when necessary.
- Do not assume the developer already understands every implementation detail.
- Present advantages, disadvantages and alternatives when making important architectural decisions.
- Clearly distinguish between implemented features and proposed features.
- Ask questions when requirements are unclear rather than making major assumptions.

The developer has final authority over all architectural, technical and implementation decisions.

---

## 8. Initial Development Instruction

When first starting this project, DO NOT write any code.

Your first task is to:

1. Read and analyze this AGENTS.md file.
2. Summarize the project objectives and technical stack.
3. Review the proposed MVP modules.
4. Discuss the initial database architecture and ERD with the developer.
5. Identify the necessary database tables and their relationships.

Potential database entities to discuss include:

- User
- Document
- ChatSession
- ChatMessage
- Flashcard
- FlashcardReview
- RevisionSchedule

These are proposed entities, not an approved final database schema.

Explain the purpose and relationships of each proposed entity.

Wait for developer approval before creating database models, migrations or application code.

**Remember: Discuss first. Get approval. Then code.**
