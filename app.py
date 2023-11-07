"""
This is the source code for the webscraper agents that use ChainLit
Features:
- Uses top N google search based on a keyword, create a JSON file, uploads it to Google Cloud Object Storage or Locally
- Continuous messaging
- Multithreading 
Written by: Antoine Ross - October 2023.
"""

from typing import Dict, Optional, Union

import autogen
from autogen import Agent, AssistantAgent, UserProxyAgent, config_list_from_json
import chainlit as cl
from chainlit.client.base import ConversationDict
import requests
import json
from dotenv import load_dotenv
import os

load_dotenv()

API_KEY = os.getenv('NEWS_API_KEY')
BASE_URL = 'https://newsapi.org/v2/everything'

WELCOME_MESSAGE = f"""Soap Opera Team 👾
\n\n
Let's make some soap opera! What topic do you want to search? (Just reply the keyword)
"""

# Agents
USER_PROXY_NAME = "Query Agent"
PROOF_READER = "Proofreader"
WRITER = "Writer"
ARTICLES = None

def get_top_articles(query, n):
    # Prepare the parameters for the API call
    params = {
        'q': query,  # search query
        'apiKey': API_KEY,
        'pageSize': n,  # number of articles to return
        'language': 'en',  # get English articles
    }
    
    # Make the API request
    response = requests.get(BASE_URL, params=params)
    
    # Check if the request was successful
    if response.status_code == 200:
        return response.json()['articles']
    else:
        raise Exception(f"Error: {response.status_code}, {response.text}")

def grab_articles(query, num):
    try:
        # Get top N articles
        articles = get_top_articles(query, num)
        # Save articles to JSON file
        return(articles)
    except Exception as e:
        print(str(e))

def extract_article_info_from_list(article_list):   
    try:
        # Initialize a string to store the extracted information
        extracted_info = ""

        # Extract and store the desired information for each article
        for article in article_list:
            description = article.get("description", "N/A")
            title = article.get("title", "N/A")
            author = article.get("author", "N/A")
            content = article.get("content", "N/A")

            # Append the information to the string
            extracted_info += f"Title: {title}\nAuthor: {author}\nDescription: {description}\nContent: {content}\n\n"

        return extracted_info

    except Exception as e:
        # Handle any exceptions
        return f"An error occurred: {str(e)}"
    
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

@cl.oauth_callback
def oauth_callback(
  provider_id: str,
  token: str,
  raw_user_data: Dict[str, str],
  default_app_user: cl.AppUser,
) -> Optional[cl.AppUser]:
  return default_app_user

@cl.on_chat_resume
async def on_chat_resume(conversation: ConversationDict):
    # Access the root messages
    root_messages = [m for m in conversation["messages"] if m["parentId"] == None]
    # Access the user_session
    cl.user_session.get("chat_profile")
    # Or just pass if you do not need to run any custom logic
    pass

@cl.on_chat_start
async def on_chat_start():
  try:
    app_user = cl.user_session.get("user")
    await cl.Message(f"Hello {app_user.username}").send()
    
    config_list = config_list_from_json(env_or_file="OAI_CONFIG_LIST")
    proof_reader = ChainlitAssistantAgent(
        name="Proof_Reader", llm_config={"config_list": config_list},
        system_message="""Proof_Reader. Help the writer and the user_proxy proofread the articles."""
    )
    writer = ChainlitAssistantAgent(
        name="Writer", llm_config={"config_list": config_list},
        system_message="""Writer. Help the User_Proxy analyse the articles. Synthesize the Articles"""
    )
    user_proxy = ChainlitUserProxyAgent(
        name="User_Proxy",
        human_input_mode="ALWAYS",
        # max_consecutive_auto_reply=3,
        # is_termination_msg=lambda x: x.get("content", "").rstrip().endswith("TERMINATE"),
        code_execution_config=False,
        system_message="""Manager. Administrate the agents on a plan. Communicate with the proofreader to proofread the output. 
        Communicate with the writer to analyse the content and ask for it to give a summary. 
                Reply CONTINUE, or the reason why the task is not solved yet."""
    )
    
    cl.user_session.set(USER_PROXY_NAME, user_proxy)
    cl.user_session.set(PROOF_READER, proof_reader)
    cl.user_session.set(WRITER, writer)
    
    # WEB-SCRAPING LOGIC
    QUERY = None
    NUM_ARTICLES = 5
    while QUERY is None:
        QUERY = await cl.AskUserMessage(content=WELCOME_MESSAGE, timeout=180, author="User_Proxy").send()
    
    print("QUERY: ", QUERY)
    articles = grab_articles(QUERY['content'], NUM_ARTICLES)
    processed_articles = extract_article_info_from_list(articles)
    
    msg = cl.Message(content=f"Processing `{QUERY['content']}`...", disable_human_feedback=True, author="User_Proxy")
    await msg.send()
    msg = cl.Message(content=f"Articles grabbed: `{articles}`...", disable_human_feedback=True, author="User_Proxy")
    await msg.send()
    
    cl.user_session.set(ARTICLES, processed_articles)
    print("Articles set...")
    
    msg = cl.Message(content=f"""This is the Soap Opera Team, please give instructions on how the Soap Opera should be structured and made. \n\n
                     Sample input: "Create a captivating soap opera scene inspired by the content of the articles. Feature characters 
                     who are entangled in a complex web of emotions, ambitions, and conflicts. Craft dialogue and actions that convey the 
                     essence of the articles, infusing drama, suspense, and emotion. Leave the audience eagerly anticipating the next twist in this gripping narrative."
                     """, 
                     disable_human_feedback=True, 
                     author="User_Proxy")
    await msg.send()
    
  except Exception as e:
    print("Error: ", e)
    pass

@cl.on_message
async def run_conversation(message: cl.Message):
  #try:
    TASK = message.content
    print("Task: ", TASK)
    proof_reader = cl.user_session.get(PROOF_READER)
    user_proxy = cl.user_session.get(USER_PROXY_NAME)
    writer = cl.user_session.get(WRITER)
    articles = cl.user_session.get(ARTICLES)

    groupchat = autogen.GroupChat(agents=[user_proxy, proof_reader, writer], messages=[], max_round=50)
    manager = autogen.GroupChatManager(groupchat=groupchat)
    
    print("Initiated GC messages... \nGC messages length: ", len(groupchat.messages))

    if len(groupchat.messages) == 0:
      message = f"""Access the output from {articles}. Create a Soap Opera based on the article details inside.
                Ensure to always check the length of the context to avoid hitting the context limit. 
                Do not express gratitude in responses.\n Instructions for creating Soap Opera:""" + TASK
      await cl.Message(content=f"""Starting agents on task of creating a Soap Opera...""").send()
      await cl.make_async(user_proxy.initiate_chat)( manager, message=message, )
    else:
      await cl.make_async(user_proxy.send)( manager, message=TASK, )
      
#   except Exception as e:
#     print("Error: ", e)
#     pass