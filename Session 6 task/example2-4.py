# basic import 
from mcp.server.fastmcp import FastMCP, Image
from mcp.server.fastmcp.prompts import base
from mcp.types import TextContent
from mcp import types
from PIL import Image as PILImage
import math
import sys
from pywinauto.application import Application
import win32gui
import win32con
import time
from win32api import GetSystemMetrics
import win32com.client
import os
from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Load environment variables
load_dotenv()

# instantiate an MCP server client
mcp = FastMCP("Calculator")

# Create shell object for SendKeys
shell = win32com.client.Dispatch("WScript.Shell")

# DEFINE TOOLS

#addition tool
@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    print("CALLED: add(a: int, b: int) -> int:")
    return int(a + b)

@mcp.tool()
def add_list(l: list) -> int:
    """Add all numbers in a list"""
    print("CALLED: add(l: list) -> int:")
    return sum(l)

# subtraction tool
@mcp.tool()
def subtract(a: int, b: int) -> int:
    """Subtract two numbers"""
    print("CALLED: subtract(a: int, b: int) -> int:")
    return int(a - b)

# multiplication tool
@mcp.tool()
def multiply(a: int, b: int) -> int:
    """Multiply two numbers"""
    print("CALLED: multiply(a: int, b: int) -> int:")
    return int(a * b)

#  division tool
@mcp.tool() 
def divide(a: int, b: int) -> float:
    """Divide two numbers"""
    print("CALLED: divide(a: int, b: int) -> float:")
    return float(a / b)

# power tool
@mcp.tool()
def power(a: int, b: int) -> int:
    """Power of two numbers"""
    print("CALLED: power(a: int, b: int) -> int:")
    return int(a ** b)

# square root tool
@mcp.tool()
def sqrt(a: int) -> float:
    """Square root of a number"""
    print("CALLED: sqrt(a: int) -> float:")
    return float(a ** 0.5)

# cube root tool
@mcp.tool()
def cbrt(a: int) -> float:
    """Cube root of a number"""
    print("CALLED: cbrt(a: int) -> float:")
    return float(a ** (1/3))

# factorial tool
@mcp.tool()
def factorial(a: int) -> int:
    """factorial of a number"""
    print("CALLED: factorial(a: int) -> int:")
    return int(math.factorial(a))

# log tool
@mcp.tool()
def log(a: int) -> float:
    """log of a number"""
    print("CALLED: log(a: int) -> float:")
    return float(math.log(a))

# remainder tool
@mcp.tool()
def remainder(a: int, b: int) -> int:
    """remainder of two numbers divison"""
    print("CALLED: remainder(a: int, b: int) -> int:")
    return int(a % b)

# sin tool
@mcp.tool()
def sin(a: int) -> float:
    """sin of a number"""
    print("CALLED: sin(a: int) -> float:")
    return float(math.sin(a))

# cos tool
@mcp.tool()
def cos(a: int) -> float:
    """cos of a number"""
    print("CALLED: cos(a: int) -> float:")
    return float(math.cos(a))

# tan tool
@mcp.tool()
def tan(a: int) -> float:
    """tan of a number"""
    print("CALLED: tan(a: int) -> float:")
    return float(math.tan(a))

# mine tool
@mcp.tool()
def mine(a: int, b: int) -> int:
    """special mining tool"""
    print("CALLED: mine(a: int, b: int) -> int:")
    return int(a - b - b)

@mcp.tool()
def create_thumbnail(image_path: str) -> Image:
    """Create a thumbnail from an image"""
    print("CALLED: create_thumbnail(image_path: str) -> Image:")
    img = PILImage.open(image_path)
    img.thumbnail((100, 100))
    return Image(data=img.tobytes(), format="png")

@mcp.tool()
def strings_to_chars_to_int(string: str) -> list[int]:
    """Return the ASCII values of the characters in a word"""
    print("CALLED: strings_to_chars_to_int(string: str) -> list[int]:")
    return [int(ord(char)) for char in string]

@mcp.tool()
def int_list_to_exponential_sum(int_list: list) -> float:
    """Return sum of exponentials of numbers in a list"""
    print("CALLED: int_list_to_exponential_sum(int_list: list) -> float:")
    # Ensure items are numbers before calculation
    try:
        # Convert each item to float, handling potential errors
        numeric_list = [float(i) for i in int_list]
        result = sum(math.exp(num) for num in numeric_list)
        print(f"DEBUG (Tool): Successfully calculated sum of exponentials: {result}")
        return result
    except ValueError as e:
        print(f"ERROR (Tool): Could not convert all items in list {int_list} to numbers: {e}")
        # Return an error indication or raise an exception that MCP might handle
        # Returning a very specific value like NaN or raising might be better
        # For now, let's return 0.0 and log the error. A more robust system
        # might return an error object.
        return 0.0 # Or raise ValueError(f"Invalid non-numeric item found in list: {e}")
    except TypeError as e:
        print(f"ERROR (Tool): Type error during exponential sum calculation for {int_list}: {e}")
        return 0.0 # Fallback

@mcp.tool()
def fibonacci_numbers(n: int) -> list:
    """Return the first n Fibonacci Numbers"""
    print("CALLED: fibonacci_numbers(n: int) -> list:")
    if n <= 0:
        return []
    fib_sequence = [0, 1]
    for _ in range(2, n):
        fib_sequence.append(fib_sequence[-1] + fib_sequence[-2])
    return fib_sequence[:n]


@mcp.tool()
async def draw_rectangle(x1: int, y1: int, x2: int, y2: int) -> dict:
    """Draw a rectangle in Paint from (x1,y1) to (x2,y2)"""
    global paint_app, shell
    try:
        if not paint_app:
            return {
                "content": [
                    TextContent(
                        type="text",
                        text="Paint is not open. Please call open_paint first."
                    )
                ]
            }
        
        # Get the Paint window
        paint_window = paint_app.window(class_name='MSPaintApp')
        print("Paint window found")
        
        # Ensure Paint window is active and maximized
        if not paint_window.has_focus():
            paint_window.set_focus()
            time.sleep(1)
        win32gui.ShowWindow(paint_window.handle, win32con.SW_MAXIMIZE)
        time.sleep(1)
        print("Paint window focused and maximized")
        
        # Get the canvas area
        canvas = paint_window.child_window(class_name='MSPaintView')
        print("Canvas found")
        
        # Select rectangle tool using keyboard sequence
        print("Starting keyboard sequence for rectangle tool")
        
        # Send Alt key
        shell.SendKeys("%")
        time.sleep(1)
        print("Alt pressed")
        
        # Send H for Home
        shell.SendKeys("h")
        time.sleep(1)
        print("H pressed")
        
        # Send SH for shapes
        shell.SendKeys("sh")
        time.sleep(1)
        print("SH pressed")
        
        # Send right arrow 4 times
        for i in range(3):
            shell.SendKeys("{RIGHT}")
            time.sleep(0.5)
            print(f"Right arrow {i+1} pressed")
        
        # Press Enter to select the rectangle tool
        shell.SendKeys("{ENTER}")
        time.sleep(1)
        print("Enter pressed to select rectangle")
        
        # Ensure we're in drawing mode by clicking on canvas first
        canvas.click_input(coords=(100, 100))  # Click in a safe area to ensure focus
        time.sleep(0.5)
        print("Clicked canvas to ensure drawing mode")
        
        # Draw the rectangle
        print(f"Starting to draw rectangle from ({x1}, {y1}) to ({x2}, {y2})")
        
        # Move to start position without clicking
        canvas.move_mouse_input(coords=(x1, y1))
        time.sleep(0.5)
        
        # Press and hold left button
        canvas.press_mouse_input(coords=(x1, y1), button='left')
        time.sleep(0.5)
        print("Mouse button pressed at start position")
        
        # Drag to end position
        canvas.move_mouse_input(coords=(x2, y2))
        time.sleep(0.5)
        print("Mouse dragged to end position")
        
        # Release button
        canvas.release_mouse_input(coords=(x2, y2), button='left')
        time.sleep(0.5)
        print("Mouse button released")
        
        return {
            "content": [
                TextContent(
                    type="text",
                    text=f"Rectangle drawn from ({x1},{y1}) to ({x2},{y2})"
                )
            ]
        }
    except Exception as e:
        print(f"Error in draw_rectangle: {str(e)}")
        return {
            "content": [
                TextContent(
                    type="text",
                    text=f"Error drawing rectangle: {str(e)}"
                )
            ]
        }

@mcp.tool()
async def add_text_in_paint(text: str) -> dict:
    """Add text in Paint"""
    global paint_app, shell
    try:
        if not paint_app:
            return {
                "content": [
                    TextContent(
                        type="text",
                        text="Paint is not open. Please call open_paint first."
                    )
                ]
            }
        
        # Get the Paint window
        paint_window = paint_app.window(class_name='MSPaintApp')
        print("Paint window found")
        
        # Ensure Paint window is active and maximized
        if not paint_window.has_focus():
            paint_window.set_focus()
            time.sleep(1)
        win32gui.ShowWindow(paint_window.handle, win32con.SW_MAXIMIZE)
        time.sleep(1)
        print("Paint window focused and maximized")
        
        # Get the canvas area
        canvas = paint_window.child_window(class_name='MSPaintView')
        print("Canvas found")
        
        # Select text tool using keyboard sequence
        print("Starting keyboard sequence for text tool")
        
        # Press Alt
        shell.SendKeys("%")
        time.sleep(1)
        print("Alt pressed")
        
        # Press H for Home tab
        shell.SendKeys("h")
        time.sleep(1)
        print("Home tab selected")
        
        # Press T for Text group
        shell.SendKeys("t")
        time.sleep(1)
        print("Text group selected")
        
        # Press A for Text tool
        shell.SendKeys("a")
        time.sleep(1)
        print("Text tool selected")
        
        # Click in the middle of the rectangle to start typing
        x_center = 1010  # Starting position (left side)
        y_text = 410    # Middle of rectangle vertically
        canvas.click_input(coords=(x_center, y_text))
        time.sleep(1)
        print(f"Clicked text position at ({x_center}, {y_text})")
        
        # Create text box by dragging - make it wider to match rectangle
        canvas.press_mouse_input(coords=(x_center, y_text))
        time.sleep(0.5)
        canvas.move_mouse_input(coords=(x_center + 500, y_text + 250))  # Text box (500px width, 250px height)
        time.sleep(0.5)
        canvas.release_mouse_input(coords=(x_center + 500, y_text + 250))
        time.sleep(1)
        print("Created text box")
        
        # Type the text passed from client
        shell.SendKeys(text)
        time.sleep(1)
        print("Text entered")
        
        # Click outside to finish text entry
        canvas.click_input(coords=(100, 100))
        time.sleep(1)
        print("Text entry completed")
        
        return {
            "content": [
                TextContent(
                    type="text",
                    text=f"Text:'{text}' added successfully"
                )
            ]
        }
    except Exception as e:
        print(f"Error in add_text_in_paint: {str(e)}")
        return {
            "content": [
                TextContent(
                    type="text",
                    text=f"Error: {str(e)}"
                )
            ]
        }

@mcp.tool()
async def open_paint() -> dict:
    """Open Microsoft Paint maximized on laptop screen"""
    global paint_app
    try:
        paint_app = Application().start('mspaint.exe')
        time.sleep(0.2)
        
        # Get the Paint window
        paint_window = paint_app.window(class_name='MSPaintApp')
        
        # Maximize the window
        win32gui.ShowWindow(paint_window.handle, win32con.SW_MAXIMIZE)
        time.sleep(0.2)
        
        return {
            "content": [
                TextContent(
                    type="text",
                    text="Paint opened successfully and maximized"
                )
            ]
        }
    except Exception as e:
        return {
            "content": [
                TextContent(
                    type="text",
                    text=f"Error opening Paint: {str(e)}"
                )
            ]
        }

@mcp.tool()
def send_gmail(recipient: str, subject: str, body: str) -> dict:
    """Send an email with calculation results. The recipient will be determined by the system configuration."""
    print("CALLED: send_gmail(recipient: str, subject: str, body: str) -> dict:")
    try:
        # Get Gmail credentials and recipient from environment variables
        sender_email = os.getenv('GMAIL_USER')
        sender_password = os.getenv('GMAIL_PASSWORD')
        actual_recipient = os.getenv('RECIPIENT_EMAIL')  # Get configured recipient
        
        if not sender_email or not sender_password or not actual_recipient:
            return {
                "content": [
                    TextContent(
                        type="text",
                        text="Error: Email configuration not found in environment variables"
                    )
                ]
            }
            
        # Create the email message
        message = MIMEMultipart()
        message["From"] = sender_email
        message["To"] = actual_recipient
        message["Subject"] = subject
        
        # Add body to email
        message.attach(MIMEText(body, "plain"))
        print("Email message created successfully")
        
        # Create SMTP session and send email
        print("Attempting to connect to Gmail SMTP server...")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            print("Connected to Gmail server")
            print("Attempting login...")
            server.login(sender_email, sender_password)
            print("Login successful")
            print("Sending message...")
            server.send_message(message)
            print("Message sent successfully")
            
        print("=== Email Send Process Completed ===\n")
        return {
            "content": [
                TextContent(
                    type="text",
                    text=f"Email sent successfully to {actual_recipient}"
                )
            ]
        }
        
    except Exception as e:
        print(f"=== Email Send Error ===")
        print(f"Error type: {type(e)}")
        print(f"Error message: {str(e)}")
        print("=== End Error Report ===\n")
        return {
            "content": [
                TextContent(
                    type="text",
                    text=f"Error sending email: {str(e)}"
                )
            ]
        }

# DEFINE RESOURCES

# Add a dynamic greeting resource
@mcp.resource("greeting://{name}")
def get_greeting(name: str) -> str:
    """Get a personalized greeting"""
    print("CALLED: get_greeting(name: str) -> str:")
    return f"Hello, {name}!"


# DEFINE AVAILABLE PROMPTS
@mcp.prompt()
def review_code(code: str) -> str:
    return f"Please review this code:\n\n{code}"
    print("CALLED: review_code(code: str) -> str:")


@mcp.prompt()
def debug_error(error: str) -> list[base.Message]:
    return [
        base.UserMessage("I'm seeing this error:"),
        base.UserMessage(error),
        base.AssistantMessage("I'll help debug that. What have you tried so far?"),
    ]

if __name__ == "__main__":
    # Check if running with mcp dev command
    print("STARTING")
    if len(sys.argv) > 1 and sys.argv[1] == "dev":
        mcp.run()  # Run without transport for dev server
    else:
        mcp.run(transport="stdio")  # Run with stdio for direct execution
