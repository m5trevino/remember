## Introduction to Tool Use

Tool use is a powerful feature that allows Large Language Models (LLMs) to interact with external resources, such as APIs, databases, and the web, to gather dynamic data they wouldn't otherwise have access to in their pre-trained (or static) state and perform actions beyond simple text generation.

Tool use bridges the gap between the data that the LLMs were trained on with dynamic data and real-world actions, which opens up a wide array of realtime use cases for us to build powerful applications with, especially with Groq's insanely fast inference speed. 🚀

## [Supported Models](https://console.groq.com/docs/tool-use#supported-models)

| Model ID | Tool Use Support? | Parallel Tool Use Support? | JSON Mode Support? |
| --- | --- | --- | --- |
| 
`moonshotai/kimi-k2-instruct`



 | Yes | Yes | Yes |
| 

`meta-llama/llama-4-scout-17b-16e-instruct`



 | Yes | Yes | Yes |
| 

`meta-llama/llama-4-maverick-17b-128e-instruct`



 | Yes | Yes | Yes |
| 

`deepseek-r1-distill-llama-70b`



 | Yes | Yes | Yes |
| 

`llama-3.3-70b-versatile`



 | Yes | Yes | Yes |
| 

`llama-3.1-8b-instant`



 | Yes | Yes | Yes |
| 

`gemma2-9b-it`



 | Yes | No | Yes |

## [Agentic Tooling](https://console.groq.com/docs/tool-use#agentic-tooling)

In addition to the models that support custom tools above, Groq also offers agentic tool systems. These are AI systems with tools like web search and code execution built directly into the system. You don't need to specify any tools yourself - the system will automatically use its built-in tools as needed.

  
[

Learn More About Agentic Tooling

Discover how to build powerful applications with real-time web search and code execution





](https://console.groq.com/docs/agentic-tooling)

## [How Tool Use Works](https://console.groq.com/docs/tool-use#how-tool-use-works)

Groq API tool use structure is compatible with OpenAI's tool use structure, which allows for easy integration. See the following cURL example of a tool use request:

  

```
curl https://api.groq.com/openai/v1/chat/completions \
-H "Content-Type: application/json" \
-H "Authorization: Bearer $GROQ_API_KEY" \
-d '{
  "model": "llama-3.3-70b-versatile",
  "messages": [
    {
      "role": "user",
      "content": "What'\''s the weather like in Boston today?"
    }
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "get_current_weather",
        "description": "Get the current weather in a given location",
        "parameters": {
          "type": "object",
          "properties": {
            "location": {
              "type": "string",
              "description": "The city and state, e.g. San Francisco, CA"
            },
            "unit": {
              "type": "string",
              "enum": ["celsius", "fahrenheit"]
            }
          },
          "required": ["location"]
        }
      }
    }
  ],
  "tool_choice": "auto"
}'
```

To integrate tools with Groq API, follow these steps:

1.  Provide tools (or predefined functions) to the LLM for performing actions and accessing external data in real-time in addition to your user prompt within your Groq API request
2.  Define how the tools should be used to teach the LLM how to use them effectively (e.g. by defining input and output formats)
3.  Let the LLM autonomously decide whether or not the provided tools are needed for a user query by evaluating the user query, determining whether the tools can enhance its response, and utilizing the tools accordingly
4.  Extract tool input, execute the tool code, and return results
5.  Let the LLM use the tool result to formulate a response to the original prompt

This process allows the LLM to perform tasks such as real-time data retrieval, complex calculations, and external API interaction, all while maintaining a natural conversation with our end user.

## [Tool Use with Groq](https://console.groq.com/docs/tool-use#tool-use-with-groq)

Groq API endpoints support tool use to almost instantly deliver structured JSON output that can be used to directly invoke functions from desired external resources.

### [Tools Specifications](https://console.groq.com/docs/tool-use#tools-specifications)

Tool use is part of the [Groq API chat completion request payload](https://console.groq.com/docs/api-reference#chat-create). Groq API tool calls are structured to be OpenAI-compatible.

### [Tool Call Structure](https://console.groq.com/docs/tool-use#tool-call-structure)

The following is an example tool call structure:

```
{
  "model": "llama-3.3-70b-versatile",
  "messages": [
    {
      "role": "system",
      "content": "You are a weather assistant. Use the get_weather function to retrieve weather information for a given location."
    },
    {
      "role": "user",
      "content": "What's the weather like in New York today?"
    }
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "Get the current weather for a location",
        "parameters": {
          "type": "object",
          "properties": {
            "location": {
              "type": "string",
              "description": "The city and state, e.g. San Francisco, CA"
            },
            "unit": {
              "type": "string",
              "enum": ["celsius", "fahrenheit"],
              "description": "The unit of temperature to use. Defaults to fahrenheit."
            }
          },
          "required": ["location"]
        }
      }
    }
  ],
  "tool_choice": "auto",
  "max_completion_tokens": 4096
}'
```

### [Tool Call Response](https://console.groq.com/docs/tool-use#tool-call-response)

The following is an example tool call response based on the above:

```
"model": "llama-3.3-70b-versatile",
"choices": [{
    "index": 0,
    "message": {
        "role": "assistant",
        "tool_calls": [{
            "id": "call_d5wg",
            "type": "function",
            "function": {
                "name": "get_weather",
                "arguments": "{\"location\": \"New York, NY\"}"
            }
        }]
    },
    "logprobs": null,
    "finish_reason": "tool_calls"
}],
```

When a model decides to use a tool, it returns a response with a `tool_calls` object containing:

-   `id`: a unique identifier for the tool call
-   `type`: the type of tool call, i.e. function
-   `name`: the name of the tool being used
-   `parameters`: an object containing the input being passed to the tool

## [Setting Up Tools](https://console.groq.com/docs/tool-use#setting-up-tools)

To get started, let's go through an example of tool use with Groq API that you can use as a base to build more tools on your own.

  

#### [Step 1: Create Tool](https://console.groq.com/docs/tool-use#step-1-create-tool)

Let's install Groq SDK, set up our Groq client, and create a function called `calculate` to evaluate a mathematical expression that we will represent as a tool.

Note: In this example, we're defining a function as our tool, but your tool can be any function or an external resource (e.g. dabatase, web search engine, external API).

  

```
1from groq import Groq
2import json
3
4# Initialize the Groq client
5client = Groq()
6# Specify the model to be used (we recommend Llama 3.3 70B)
7MODEL = 'llama-3.3-70b-versatile'
8
9def calculate(expression):
10    """Evaluate a mathematical expression"""
11    try:
12        # Attempt to evaluate the math expression
13        result = eval(expression)
14        return json.dumps({"result": result})
15    except:
16        # Return an error message if the math expression is invalid
17        return json.dumps({"error": "Invalid expression"})
```

#### [Step 2: Pass Tool Definition and Messages to Model](https://console.groq.com/docs/tool-use#step-2-pass-tool-definition-and-messages-to-model)

Next, we'll define our `calculate` tool within an array of available `tools` and call our Groq API chat completion. You can read more about tool schema and supported required and optional fields above in [Tool Specifications](https://console.groq.com/docs/tool-use#tool-call-and-tool-response-structure).

By defining our tool, we'll inform our model about what our tool does and have the model decide whether or not to use the tool. We should be as descriptive and specific as possible for our model to be able to make the correct tool use decisions.

In addition to our `tools` array, we will provide our `messages` array (e.g. containing system prompt, assistant prompt, and/or user prompt).

#### [Step 3: Receive and Handle Tool Results](https://console.groq.com/docs/tool-use#step-3-receive-and-handle-tool-results)

After executing our chat completion, we'll extract our model's response and check for tool calls.

If the model decides that no tools should be used and does not generate a tool or function call, then the response will be a normal chat completion (i.e. `response_message = response.choices[0].message`) with a direct model reply to the user query.

If the model decides that tools should be used and generates a tool or function call, we will:

1.  Define available tool or function
2.  Add the model's response to the conversation by appending our message
3.  Process the tool call and add the tool response to our message
4.  Make a second Groq API call with the updated conversation
5.  Return the final response

  

```
1# imports calculate function from step 1
2def run_conversation(user_prompt):
3    # Initialize the conversation with system and user messages
4    messages=[
5        {
6            "role": "system",
7            "content": "You are a calculator assistant. Use the calculate function to perform mathematical operations and provide the results."
8        },
9        {
10            "role": "user",
11            "content": user_prompt,
12        }
13    ]
14    # Define the available tools (i.e. functions) for our model to use
15    tools = [
16        {
17            "type": "function",
18            "function": {
19                "name": "calculate",
20                "description": "Evaluate a mathematical expression",
21                "parameters": {
22                    "type": "object",
23                    "properties": {
24                        "expression": {
25                            "type": "string",
26                            "description": "The mathematical expression to evaluate",
27                        }
28                    },
29                    "required": ["expression"],
30                },
31            },
32        }
33    ]
34    # Make the initial API call to Groq
35    response = client.chat.completions.create(
36        model=MODEL, # LLM to use
37        messages=messages, # Conversation history
38        stream=False,
39        tools=tools, # Available tools (i.e. functions) for our LLM to use
40        tool_choice="auto", # Let our LLM decide when to use tools
41        max_completion_tokens=4096 # Maximum number of tokens to allow in our response
42    )
43    # Extract the response and any tool call responses
44    response_message = response.choices[0].message
45    tool_calls = response_message.tool_calls
46    if tool_calls:
47        # Define the available tools that can be called by the LLM
48        available_functions = {
49            "calculate": calculate,
50        }
51        # Add the LLM's response to the conversation
52        messages.append(response_message)
53
54        # Process each tool call
55        for tool_call in tool_calls:
56            function_name = tool_call.function.name
57            function_to_call = available_functions[function_name]
58            function_args = json.loads(tool_call.function.arguments)
59            # Call the tool and get the response
60            function_response = function_to_call(
61                expression=function_args.get("expression")
62            )
63            # Add the tool response to the conversation
64            messages.append(
65                {
66                    "tool_call_id": tool_call.id, 
67                    "role": "tool", # Indicates this message is from tool use
68                    "name": function_name,
69                    "content": function_response,
70                }
71            )
72        # Make a second API call with the updated conversation
73        second_response = client.chat.completions.create(
74            model=MODEL,
75            messages=messages
76        )
77        # Return the final response
78        return second_response.choices[0].message.content
79# Example usage
80user_prompt = "What is 25 * 4 + 10?"
81print(run_conversation(user_prompt))
```

## [Parallel Tool Use](https://console.groq.com/docs/tool-use#parallel-tool-use)

We learned about tool use and built single-turn tool use examples above. Now let's take tool use a step further and imagine a workflow where multiple tools can be called simultaneously, enabling more efficient and effective responses.

This concept is known as **parallel tool use** and is key for building agentic workflows that can deal with complex queries, which is a great example of where inference speed becomes increasingly important (and thankfully we can access fast inference speed with Groq API).

Here's an example of parallel tool use with a tool for getting the temperature and the tool for getting the weather condition to show parallel tool use with Groq API in action:

  

  

```
1import json
2from groq import Groq
3import os
4
5# Initialize Groq client
6client = Groq()
7model = "llama-3.3-70b-versatile"
8
9# Define weather tools
10def get_temperature(location: str):
11    # This is a mock tool/function. In a real scenario, you would call a weather API.
12    temperatures = {"New York": "22°C", "London": "18°C", "Tokyo": "26°C", "Sydney": "20°C"}
13    return temperatures.get(location, "Temperature data not available")
14
15def get_weather_condition(location: str):
16    # This is a mock tool/function. In a real scenario, you would call a weather API.
17    conditions = {"New York": "Sunny", "London": "Rainy", "Tokyo": "Cloudy", "Sydney": "Clear"}
18    return conditions.get(location, "Weather condition data not available")
19
20# Define system messages and tools
21messages = [
22    {"role": "system", "content": "You are a helpful weather assistant."},
23    {"role": "user", "content": "What's the weather and temperature like in New York and London? Respond with one sentence for each city. Use tools to get the information."},
24]
25
26tools = [
27    {
28        "type": "function",
29        "function": {
30            "name": "get_temperature",
31            "description": "Get the temperature for a given location",
32            "parameters": {
33                "type": "object",
34                "properties": {
35                    "location": {
36                        "type": "string",
37                        "description": "The name of the city",
38                    }
39                },
40                "required": ["location"],
41            },
42        },
43    },
44    {
45        "type": "function",
46        "function": {
47            "name": "get_weather_condition",
48            "description": "Get the weather condition for a given location",
49            "parameters": {
50                "type": "object",
51                "properties": {
52                    "location": {
53                        "type": "string",
54                        "description": "The name of the city",
55                    }
56                },
57                "required": ["location"],
58            },
59        },
60    }
61]
62
63# Make the initial request
64response = client.chat.completions.create(
65    model=model, messages=messages, tools=tools, tool_choice="auto", max_completion_tokens=4096, temperature=0.5
66)
67
68response_message = response.choices[0].message
69tool_calls = response_message.tool_calls
70
71# Process tool calls
72messages.append(response_message)
73
74available_functions = {
75    "get_temperature": get_temperature,
76    "get_weather_condition": get_weather_condition,
77}
78
79for tool_call in tool_calls:
80    function_name = tool_call.function.name
81    function_to_call = available_functions[function_name]
82    function_args = json.loads(tool_call.function.arguments)
83    function_response = function_to_call(**function_args)
84
85    messages.append(
86        {
87            "role": "tool",
88            "content": str(function_response),
89            "tool_call_id": tool_call.id,
90        }
91    )
92
93# Make the final request with tool call results
94final_response = client.chat.completions.create(
95    model=model, messages=messages, tools=tools, tool_choice="auto", max_completion_tokens=4096
96)
97
98print(final_response.choices[0].message.content)
```

  

## [Error Handling](https://console.groq.com/docs/tool-use#error-handling)

Groq API tool use is designed to verify whether a model generates a valid tool call object. When a model fails to generate a valid tool call object, Groq API will return a 400 error with an explanation in the "failed\_generation" field of the JSON body that is returned.

### [Next Steps](https://console.groq.com/docs/tool-use#next-steps)

For more information and examples of working with multiple tools in parallel using Groq API and Instructor, see our Groq API Cookbook tutorial [here](https://github.com/groq/groq-api-cookbook/blob/main/tutorials/parallel-tool-use/parallel-tool-use.ipynb).

  

## [Tool Use with Structured Outputs (Python)](https://console.groq.com/docs/tool-use#tool-use-with-structured-outputs-python)

Groq API offers best-effort matching for parameters, which means the model could occasionally miss parameters or misinterpret types for more complex tool calls. We recommend the [Instuctor](https://python.useinstructor.com/hub/groq/) library to simplify the process of working with structured data and to ensure that the model's output adheres to a predefined schema.

Here's an example of how to implement tool use using the Instructor library with Groq API:

  

```
pip install instructor pydantic
```

  

```
1import instructor
2from pydantic import BaseModel, Field
3from groq import Groq
4
5# Define the tool schema
6tool_schema = {
7    "name": "get_weather_info",
8    "description": "Get the weather information for any location.",
9    "parameters": {
10        "type": "object",
11        "properties": {
12            "location": {
13                "type": "string",
14                "description": "The location for which we want to get the weather information (e.g., New York)"
15            }
16        },
17        "required": ["location"]
18    }
19}
20
21# Define the Pydantic model for the tool call
22class ToolCall(BaseModel):
23    input_text: str = Field(description="The user's input text")
24    tool_name: str = Field(description="The name of the tool to call")
25    tool_parameters: str = Field(description="JSON string of tool parameters")
26
27class ResponseModel(BaseModel):
28    tool_calls: list[ToolCall]
29
30# Patch Groq() with instructor
31client = instructor.from_groq(Groq(), mode=instructor.Mode.JSON)
32
33def run_conversation(user_prompt):
34    # Prepare the messages
35    messages = [
36        {
37            "role": "system",
38            "content": f"You are an assistant that can use tools. You have access to the following tool: {tool_schema}"
39        },
40        {
41            "role": "user",
42            "content": user_prompt,
43        }
44    ]
45
46    # Make the Groq API call
47    response = client.chat.completions.create(
48        model="llama-3.3-70b-versatile",
49        response_model=ResponseModel,
50        messages=messages,
51        temperature=0.5,
52        max_completion_tokens=1000,
53    )
54
55    return response.tool_calls
56
57# Example usage
58user_prompt = "What's the weather like in San Francisco?"
59tool_calls = run_conversation(user_prompt)
60
61for call in tool_calls:
62    print(f"Input: {call.input_text}")
63    print(f"Tool: {call.tool_name}")
64    print(f"Parameters: {call.tool_parameters}")
65    print()
```

### [Benefits of Using Structured Outputs](https://console.groq.com/docs/tool-use#benefits-of-using-structured-outputs)

-   Type Safety: Pydantic models ensure that output adheres to the expected structure, reducing the risk of errors.
-   Automatic Validation: Instructor automatically validates the model's output against the defined schema.

### [Next Steps](https://console.groq.com/docs/tool-use#next-steps)

For more information and examples of working with structured outputs using Groq API and Instructor, see our Groq API Cookbook tutorial [here](https://github.com/groq/groq-api-cookbook/blob/main/tutorials/structured-output-instructor/structured_output_instructor.ipynb).

## [Streaming Tool Use](https://console.groq.com/docs/tool-use#streaming-tool-use)

The Groq API also offers streaming tool use, where you can stream tool use results to the client as they are generated.

```
from groq import Groq
import json

client = Groq()

async def main():
    stream = await client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant.",
            },
            {
                "role": "user",
                # We first ask it to write a Poem, to show the case where there's text output before function calls, since that is also supported
                "content": "What is the weather in San Francisco and in Tokyo? First write a short poem.",
            },
        ],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "get_current_weather",
                    "description": "Get the current weather in a given location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "The city and state, e.g. San Francisco, CA"
                            },
                            "unit": {
                                "type": "string",
                                "enum": ["celsius", "fahrenheit"]
                            }
                        },
                        "required": ["location"]
                    }
                }
            }
        ],
        model="llama-3.3-70b-versatile",
        temperature=0.5,
        stream=True
    )

    async for chunk in stream:
        print(json.dumps(chunk.model_dump()) + "\n")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

## [Best Practices](https://console.groq.com/docs/tool-use#best-practices)

-   Provide detailed tool descriptions for optimal performance.
-   We recommend tool use with the Instructor library for structured outputs.
-   Use the fine-tuned Llama 3 models by Groq or the Llama 3.1 models for your applications that require tool use.
-   Implement a routing system when using fine-tuned models in your workflow.
-   Handle tool execution errors by returning error messages with `"is_error": true`.

### Was this page helpful?