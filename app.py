"""
This is the source code for the webscraper agents that use ChainLit
Features:
- Uses top N google search based on a keyword, create a JSON file, uploads it to Google Cloud Object Storage or Locally
- Capable of asking Reddit for questions
- Continuous messaging
- Multithreading 
Written by: Antoine Ross - October 2023.
"""

import os
from typing import Dict, Optional, Union
from dotenv import load_dotenv, find_dotenv

import chainlit as cl
from chainlit.client.base import ConversationDict
from chainlit.types import AskFileResponse
from langchain.document_loaders import PyPDFLoader, TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.chains import ConversationalRetrievalChain

import autogen
from autogen import Agent, AssistantAgent, UserProxyAgent, config_list_from_json
from redditAPI import grab_articles

load_dotenv(find_dotenv())

CONTEXT = """- Task: ArticleGPT specializes in creating SEO-optimized articles specifically tailored for [Medium.com](http://medium.com/). The target audience are people who are looking to get started with learning AI & Machine Learning and LLM’s for their use-case.
    
    
    Output Specifications: 
    
    • Output Style and Format: Craft articles that fit [Medium.com](http://medium.com/)'s style, being straightforward and concise. Ensure grammatical accuracy, coherence, and stylistic refinement. Use hooks and effective whitespace management to maintain reader's attention. Humor and Sarcasm: Including a directive for humor and sarcasm to utilize rhetorical devices, which could make the text feel more human-like. 
    
    • Tone: The tone is conversational and likable, similar to Morgan Freeman's speech style.
    
    • Titles and Subheadings: Create titles and subheadings that are Impactful, concise and effectively capturing the content's essence. 
    
    • Titles: 5-9 words, with numbers for higher click-through rates. Prefer negative or neutral tones. 
    
    • Headlines: Structure in two parts, main and sub-headline. 
    
    • Subheadings: Spark curiosity with questions, action words, and numbers; emphasize benefits. 
    
    • Content balancing simplicity, engagement, and SEO optimization for Medium.
    
    • 
    
    Sample output:
    
    Title
    
    Subheading 1
    
    paragraph 1: Explain concisely the core of the article. How it can be useful for their use-case. (2-3 sentences)
    
    Subheading 2
    
    paragraph 2: Tell the readers how doing/having three things can dramatically improve results. (1-2 sentences)
    
    [3 bullet points or 3 numbered list to support paragraph 2]
    
    paragraph 3: summarize the bullet points and how it can be useful for the reader. (1-2 sentences)
    
    Subheading 3
    
    paragraph 4: Concluding Anecdote or Opinion: Requesting a final 'personal' touch is intended to leave the reader with a sense of individual perspective, something that machine-generated text often lacks. (2-3 sentences)
    """

# Agents
USER_PROXY_NAME = "User Proxy"
PROOF_READER = "Proofreader"
WRITER = "Writer"
EMOTIONAL_STRATEGIST = "Emotional Impact Strategist"
NARRATIVE_DESIGNER = "Narrative Designer"
STYLIST = "Style Specialist"
ARTICLES = None

text_splitter = RecursiveCharacterTextSplitter(chunk_size=8192, chunk_overlap=100)

def load_articles(file_path):
    try:
        with open(file_path, 'r') as file:
            article = file.read()
        return article
    except FileNotFoundError:
        print("File not found")
        return None

# Function to process the file
def process_file(file: AskFileResponse):
    import tempfile

    if file.type == "text/plain":
        Loader = TextLoader
    elif file.type == "application/pdf":
        Loader = PyPDFLoader

    with tempfile.NamedTemporaryFile(mode="wb", delete=False) as tempfile:
        if file.type == "text/plain":
            tempfile.write(file.content)
        elif file.type == "application/pdf":
            with open(tempfile.name, "wb") as f:
                f.write(file.content)

        loader = Loader(tempfile.name)
        documents = loader.load()
        docs = text_splitter.split_documents(documents)
        for i, doc in enumerate(docs):
            doc.metadata["source"] = f"source_{i}"
        cl.user_session.set("docs", docs)
        return docs
    
async def ask_helper(func, **kwargs):
    res = await func(**kwargs).send()
    while not res:
        res = await func(**kwargs).send()
    return res

class ChainlitAssistantAgent(AssistantAgent):
    """
    Wrapper for AutoGens Assistant Agent
    """
    def send(
        self,
        message: Union[Dict, str],
        recipient: Agent,
        request_reply: Optional[bool] = None,
        silent: Optional[bool] = False,
    ) -> bool:
        cl.run_sync(
            cl.Message(
                content=f'*Sending message to "{recipient.name}":*\n\n{message}',
                author=self.name,
            ).send()
        )
        super(ChainlitAssistantAgent, self).send(
            message=message,
            recipient=recipient,
            request_reply=request_reply,
            silent=silent,
        )
class ChainlitUserProxyAgent(UserProxyAgent):
    """
    Wrapper for AutoGens UserProxy Agent. Simplifies the UI by adding CL Actions. 
    """
    def get_human_input(self, prompt: str) -> str:
        if prompt.startswith(
            "Provide feedback to chat_manager. Press enter to skip and use auto-reply"
        ):
            res = cl.run_sync(
                ask_helper(
                    cl.AskActionMessage,
                    content="Continue or provide feedback?",
                    actions=[
                        cl.Action( name="continue", value="continue", label="✅ Continue" ),
                        cl.Action( name="feedback",value="feedback", label="💬 Provide feedback"),
                        cl.Action( name="exit",value="exit", label="🔚 Exit Conversation" )
                    ],
                )
            )
            if res.get("value") == "continue":
                return ""
            if res.get("value") == "exit":
                return "exit"

        reply = cl.run_sync(ask_helper(cl.AskUserMessage, content=prompt, timeout=60))

        return reply["content"].strip()

    def send(
        self,
        message: Union[Dict, str],
        recipient: Agent,
        request_reply: Optional[bool] = None,
        silent: Optional[bool] = False,
    ):
        cl.run_sync(
            cl.Message(
                content=f'*Sending message to "{recipient.name}"*:\n\n{message}',
                author=self.name,
            ).send()
        )
        super(ChainlitUserProxyAgent, self).send(
            message=message,
            recipient=recipient,
            request_reply=request_reply,
            silent=silent,
        )

config_list = autogen.config_list_from_dotenv(
    dotenv_file_path='.env',
    model_api_key_map={
        "gpt-3.5-turbo": "OPENAI_API_KEY",
    },
    filter_dict={
        "model": {
            "gpt-3.5-turbo",
        }
    }
)

@cl.action_callback("confirm_action")
async def on_action(action: cl.Action):
    if action.value == "everything":
        content = "everything"
    elif action.value == "top-headlines":
        content = "top_headlines"
    else:
        await cl.ErrorMessage(content="Invalid action").send()
        return

    prev_msg = cl.user_session.get("url_actions")  # type: cl.Message
    if prev_msg:
        await prev_msg.remove_actions()
        cl.user_session.set("url_actions", None)

    await cl.Message(content=content).send()
    
@cl.on_chat_start
async def on_chat_start():
  OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
  

  try:
    # app_user = cl.user_session.get("user")
    # await cl.Message(f"Hello {app_user.username}").send()
    # config_list = config_list_from_json(env_or_file="OAI_CONFIG_LIST")
    llm_config = {"config_list": config_list, "api_key": OPENAI_API_KEY, "seed": 42, "request_timeout": 60, "retry_wait_time": 60}
    proof_reader = ChainlitAssistantAgent(
        name="Proof_Reader", llm_config=llm_config,
        system_message="""Proofreader. Focuses on grammatical accuracy and stylistic refinement, ensuring that articles meet Medium.com's standards.
Enhances clarity and coherence while maintaining a conversational, likable tone akin to Morgan Freeman's speech style.
Assures the use of effective hooks and whitespace management to keep the reader's attention.
Ensures articles are straightforward, concise, and free of filler words, with minimal use of humor and sarcasm."""
    )
    writer = ChainlitAssistantAgent(
        name="Writer", llm_config=llm_config,
        system_message="""Writer. Develops SEO-optimized, engaging content tailored for Medium.com's audience interested in AI & Machine Learning.
Writes with a conversational and likable tone, ensuring simplicity and engagement.
Crafts impactful, concise titles and subheadings, with titles of 5-9 words incorporating numbers, and negative or neutral tones.
Structures content with effective subheadings and bullet points to facilitate reader understanding and engagement."""
    )
    narrative_designer = ChainlitAssistantAgent(
        name="Narrative_Designer", llm_config=llm_config,
        system_message="""Narrative Designer. Structures the article to maintain engagement and curiosity, using questions, action words, and numbers in subheadings.
Collaborates with the Writer and Emotional Impact Strategist to ensure the narrative is clear, concise, and resonates with the target audience.
Advises on the narrative flow to maintain reader interest and optimize for SEO."""
    )
    stylist = ChainlitAssistantAgent(
        name="Style_Specialist", llm_config=llm_config,
        system_message="""Style Specialist. Refines tone and style to be conversational and likable, aligning with the Morgan Freeman style.
Ensures the use of effective rhetoric, including minimal humor and sarcasm, to enhance readability and engagement.
Collaborates with the Writer and Proofreader to ensure stylistic consistency throughout the article."""
    )
    emotional_impact_strategist = ChainlitAssistantAgent(
        name="Emotional_Strategist", llm_config=llm_config,
        system_message="""Develops strategies for titles and subheadings that are impactful, concise, and evoke curiosity.
Advises on incorporating emotional cues that resonate with the audience's interests in AI and Machine Learning.
Collaborates with the Narrative Designer and Style Specialist to ensure a unified approach in content framing.
        """
    )
    user_proxy = ChainlitUserProxyAgent(
        name="User_Proxy",
        human_input_mode="ALWAYS",
        llm_config=llm_config,
        # max_consecutive_auto_reply=3,
        # is_termination_msg=lambda x: x.get("content", "").rstrip().endswith("TERMINATE"),
        code_execution_config=False,
        system_message="""User Proxy. Provides feedback on the article's effectiveness in engaging readers interested in AI and Machine Learning.
Ensures the article meets overall objectives and resonates with the intended audience.
Relays audience and management preferences to the team for necessary adjustments."""
    )
    
    cl.user_session.set(USER_PROXY_NAME, user_proxy)
    cl.user_session.set(PROOF_READER, proof_reader)
    cl.user_session.set(WRITER, writer)
    cl.user_session.set(STYLIST, stylist)
    cl.user_session.set(NARRATIVE_DESIGNER, narrative_designer)
    cl.user_session.set(EMOTIONAL_STRATEGIST, emotional_impact_strategist)
    
    doc = cl.Action( name="doc", value="doc", label="Document" )
    no_doc = cl.Action( name="no_doc", value="no_doc", label="NoDocument" )
    idea = cl.Action( name="Idea", value="Idea", label="Idea" )
    no_idea = cl.Action( name="NoIdea", value="NoIdea", label="NoIdea" )
    idea_actions = [idea, no_idea]
    doc_actions = [doc, no_doc]
    
    IDEA_option = cl.AskActionMessage(
        content="Hi, let’s generate some Article ideas. Would you like to generate ideas from Reddit, or continue?",
        actions=idea_actions,
    )
    await IDEA_option.send()
    
    IDEA_option = IDEA_option.content.split()[-1]
    if IDEA_option == "Idea":
        print("Using document...")
        TOPIC = None
        while TOPIC is None:
            TOPIC = await cl.AskUserMessage(content="What topic would you like to make an Article about? [Only send one keyword.]", timeout=180).send()

        print("Topic: ", TOPIC['content'])
        msg = cl.Message(
        content=f"Processing data from Reddit...", disable_human_feedback=True
        )
        await msg.send()
        
        articles = grab_articles(TOPIC['content'])
        msg = cl.Message(
            content=f"Content from Reddit loaded: \n{articles}", disable_human_feedback=True
        )
        await msg.send()
    elif IDEA_option == "NoIdea":
        article_path = "articles.txt"
        articles = load_articles(article_path)
    print("Articles grabbed.")
    
    msg = cl.Message(content=f"Processing `{articles}`...", disable_human_feedback=True, author="User_Proxy")
    await msg.send()
    
    cl.user_session.set(ARTICLES, articles)
    print("Articles set...")
    
    msg = cl.Message(content=f"""This is the Article Generation Team, please give a topic to create an Article about.""", 
                     disable_human_feedback=True, 
                     author="User_Proxy")
    await msg.send()
    
  except Exception as e:
    print("Error: ", e)
    pass

@cl.on_message
async def run_conversation(message: cl.Message):
  #try:
    MESSAGE = message.content
    print("Task: ", MESSAGE)
    proof_reader = cl.user_session.get(PROOF_READER)
    user_proxy = cl.user_session.get(USER_PROXY_NAME)
    writer = cl.user_session.get(WRITER)
    stylist = cl.user_session.get(STYLIST)
    narrative_designer = cl.user_session.get(NARRATIVE_DESIGNER)
    emotional_impact_strategist = cl.user_session.get(EMOTIONAL_STRATEGIST)
    articles = cl.user_session.get(ARTICLES)

    groupchat = autogen.GroupChat(agents=[user_proxy, proof_reader, writer,stylist, narrative_designer,emotional_impact_strategist  ], messages=[], max_round=50)
    manager = autogen.GroupChatManager(groupchat=groupchat)
    
    print("Initiated GC messages... \nGC messages length: ", len(groupchat.messages))

    if len(groupchat.messages) == 0:
      message = f"""Use this content as background for the articles you will make: {articles}. 
                First create 10 ideas, then 5, then 3, then 1.
                Finalize the ideas with the planner and make sure to follow the criteria of choosing based on: "What will be the most dramatic, emotional and entertaining idea".
                Do not express gratitude in responses.
                \nThe topic of the article will be about: """ + MESSAGE + """The final output should look like: \n""" + CONTEXT
      await cl.Message(content=f"""Starting agents on task of creating a Article...""").send()
      await cl.make_async(user_proxy.initiate_chat)( manager, message=message, )
    else:
      await cl.make_async(user_proxy.send)( manager, message=MESSAGE, )
      
#   except Exception as e:
#     print("Error: ", e)
#     pass