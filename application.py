from sqlalchemy import create_engine
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from passlib.apps import custom_app_context as pwd_context
from tempfile import mkdtemp

from helpers import *

# configure application
app = Flask(__name__)

# ensure responses aren't cached
if app.config["DEBUG"]:
    @app.after_request
    def after_request(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Expires"] = 0
        response.headers["Pragma"] = "no-cache"
        return response

# custom filter
app.jinja_env.filters["usd"] = usd

# configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# configure CS50 Library to use SQLite database
engine = create_engine('sqlite:///:memory:', echo=True)

def port_val(portfolio_dict):
    """Current total value of stock in portfolio
    called from the index route and the buy route
    which both use the index.html template"""

    sum = 0
    for stock in portfolio_dict:
        sum = sum + stock['quantity'] * lookup(stock['symbol'])['price']
    return sum

def form_validated(symbol_field_entry, quantity_field_entry):
    """Ensure form entries are non empty and quantity >= 1"""
    if not symbol_field_entry:
        return "must provide symbol"
    elif not quantity_field_entry:
        return "must provide quantity"
    else:
        # ensure quantity is an integer of 1 or greater
        try:
            quantity = int(quantity_field_entry)
        except:
            return "quantity must be an integer"
        if quantity < 1:
            return "quantity must be 1 or more"
        else:
            return True


def proceed_with_purchase(symbol, quantity):
    """Ensure stock code is valid,
    ensure there is enough cash to make purchase,
    updating tables
    and returning to updated index page"""

    stock_dict = lookup(symbol)
    if stock_dict is None:
        return apology("invalid stock symbol")
    else:
        rows = db.execute("SELECT cash FROM users\
        WHERE id = :id",\
        id = session["user_id"])

        available_cash = rows[0]["cash"]
        stock_price = stock_dict["price"]
        symbol = stock_dict["symbol"]

        # is there enough cash for this transaction?
        if int(quantity) * stock_price <= available_cash:
            new_balance = available_cash - int(quantity) * stock_price
            cash_balance = new_balance

            # update cash balance in users table
            db.execute("UPDATE users SET cash = :cash\
            WHERE id = :id",\
            cash = new_balance,\
            id = session['user_id'])

            # insert new row into transaction table
            db.execute("INSERT INTO transactions\
            (user_id, quantity, symbol, price)\
            VALUES (:user_id, :quantity, :symbol, :price)",\
            user_id = session['user_id'],\
            quantity = quantity,\
            symbol = symbol,\
            price = stock_price)

            # update portfolio table
            # find rows for current user with chosen stock
            rows = db.execute(" SELECT * FROM portfolio\
            WHERE user_id = :user_id AND symbol = :symbol ",\
            user_id = session['user_id'],\
            symbol = symbol)

            if len(rows) == 0:
                db.execute("INSERT INTO portfolio \
                (user_id, symbol, quantity)\
                VALUES (:user_id, :symbol, :quantity)",\
                user_id = session['user_id'],\
                symbol = symbol,\
                quantity = quantity)
            else:
                db.execute("UPDATE portfolio SET quantity = :quantity\
                WHERE user_id = :user_id AND symbol = :symbol ",\
                quantity = int(quantity) + rows[0]['quantity'],\
                user_id = session['user_id'],\
                symbol = symbol)

            # update portfolio_dict before rendering index.html
            portfolio_dict = db.execute("SELECT * FROM portfolio \
            WHERE user_id = :user_id",\
            user_id = session["user_id"])

            # back to index page
            return render_template("index.html",\
            portfolio = portfolio_dict,\
            lookup = lookup,\
            usd = usd,\
            cash_balance = cash_balance,\
            portfolio_value = port_val(portfolio_dict))
        else:
            return apology("not enough cash")



def proceed_with_sale(symbol, quantity):
    """Ensure stock is in portfolio, not attempting to sell more stock than there are in portfolio,
    updating tables
    and returning to updated index page"""

    stock_dict = lookup(symbol)
    if stock_dict is None:
        return apology("invalid stock symbol")
    else:
        # ensure stock is in portfolio
        stock_in_portfolio = db.execute("SELECT * FROM portfolio WHERE user_id = :user_id AND symbol = :symbol",\
        user_id = session['user_id'],\
        symbol = stock_dict['symbol'])

        if len(stock_in_portfolio) == 0:
            return apology("this stock is not in your portfolio")
        else:
            portfolio_quantity = stock_in_portfolio[0]['quantity']
            if int(quantity) > portfolio_quantity:
                return apology("selling more stock than you actually have")
            else:
                # update transactions table with negative quantity
                db.execute(\
                "INSERT INTO transactions (user_id, quantity, symbol, price)\
                VALUES (:user_id, :quantity, :symbol, :price)",\
                user_id = session['user_id'],\
                quantity = -int(quantity),\
                symbol = stock_dict['symbol'],\
                price = stock_dict['price'])

                user_cash = db.execute("SELECT cash FROM users WHERE id = :id",\
                id = session["user_id"])
                cash_balance = user_cash[0]["cash"]

                # update users table with new cash value
                db.execute("UPDATE users SET cash = :cash WHERE id = :id",\
                cash = cash_balance + int(quantity) * stock_dict['price'],\
                id = session['user_id'])

                # update portfolio table
                stock_in_portfolio = db.execute("SELECT * FROM portfolio\
                WHERE user_id = :user_id AND symbol = :symbol",\
                user_id = session['user_id'], symbol = stock_dict['symbol'])

                portfolio_quantity = stock_in_portfolio[0]['quantity']
                updated_quantity = portfolio_quantity - int(quantity)

                db.execute("UPDATE portfolio SET quantity = :quantity\
                WHERE user_id = :user_id AND symbol = :symbol ",\
                quantity = updated_quantity,\
                user_id = session['user_id'],\
                symbol = stock_dict["symbol"])

                if updated_quantity == 0:
                    db.execute("DELETE FROM portfolio\
                    WHERE (symbol = :symbol)", symbol = stock_dict["symbol"])
                else:
                    db.execute("UPDATE portfolio SET quantity = :quantity\
                    WHERE user_id = :user_id AND symbol = :symbol ",\
                    quantity = updated_quantity,\
                    user_id = session['user_id'],\
                    symbol = stock_dict["symbol"])

                # update portfolio table so that correct
                stock_in_portfolio = db.execute("SELECT * FROM portfolio\
                WHERE user_id = :user_id",\
                user_id = session['user_id'])

            return render_template("index.html",\
            portfolio = stock_in_portfolio,\
            lookup = lookup,\
            usd = usd,\
            cash_balance = cash_balance,\
            portfolio_value = port_val(stock_in_portfolio))



@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    # =====================
    # for the user currently logged in
    # display HTML table summarizing:

    # displays portfolio of  stocks the user owns
    # cash total
    # total of cash and value of portfolio
    # and the option to buy and sell shares

    portfolio_dict = db.execute("SELECT * FROM portfolio \
    WHERE user_id = :user_id",\
    user_id = session["user_id"])
    rows = db.execute("SELECT cash FROM users WHERE id = :id", id = session["user_id"])
    cash_balance = rows[0]["cash"]

    if request.method == "POST":
        # validate form and TODO

        # to begin with I'm just printing form name and value to console

        # print()
        # print(request.form)
        # print(dict(request.form))


        augmented_symbol = next(iter(dict(request.form)))
        symbol = augmented_symbol[1:]
        quantity = int(dict(request.form)[str(augmented_symbol)][0])
        buy_or_sell = augmented_symbol[0]

        print()
        print("augmented symbol is")
        print(augmented_symbol)
        print(type(augmented_symbol))
        print("symbol is")
        print(symbol)
        print(type(symbol))
        print("quantity is")
        print(quantity)
        print(type(quantity))
        print("buy or sell?")
        print(buy_or_sell)
        print(type(buy_or_sell))
        print()

        if buy_or_sell == 'B':
            return proceed_with_purchase(symbol, quantity)
        elif buy_or_sell == "S":
            return proceed_with_sale(symbol, quantity)
        else:
            return apology("something's really gone wrong")

        return apology("output to console")

    else:
        return render_template("index.html",\
        portfolio = portfolio_dict,\
        lookup = lookup,\
        usd = usd,\
        cash_balance = cash_balance,\
        portfolio_value = port_val(portfolio_dict))

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in."""

    # forget any user_id
    session.clear()

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        # ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")

        # query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # ensure username exists and password is correct
        if len(rows) != 1 or not pwd_context.verify(request.form.get("password"), rows[0]["hash"]):
            return apology("invalid username and/or password")

        # remember which user has logged in
        session["user_id"] = rows[0]["id"]
        username = db.execute("SELECT username FROM users WHERE id = :id", id=session["user_id"])

        return redirect(url_for("index"))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user."""

    # forget any user_id
    session.clear()

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        # ensure passwords were submitted and identical
        elif not (request.form.get("pwd") and request.form.get("confirm_pwd")):
            return apology("must provide password twice")

        elif request.form.get("pwd") != request.form.get("confirm_pwd"):
            return apology("passwords must match")

        hash = pwd_context.hash(request.form.get("pwd"))

        # create new user record in database
        db.execute("INSERT INTO users (username, hash) VALUES(:username, :hash)", username = request.form["username"], hash = hash)

        # find login id of registering user
        id = db.execute("SELECT id FROM users WHERE username = :username", username = request.form.get("username"))

        # remember which user has logged in
        session["user_id"] = id[0]["id"]

        # redirect user to home page
        return redirect(url_for("index"))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/logout")
def logout():
    """Log user out."""
    # forget any user_id
    session.clear()
    # redirect user to login form
    return redirect(url_for("login"))


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # ensure stock code was submitted
        if not request.form.get("symbol"):
            return apology("must provide stock symbol")
        stock_dict = lookup(request.form.get("symbol"))
        # ensure stock code is valid
        if stock_dict is None:
            return apology("invalid stock symbol")
        return render_template("show_quote.html", name = stock_dict["name"], symbol = stock_dict["symbol"], price = usd(stock_dict["price"]))
    else:
        return render_template("quote.html", symbol = "stock_dict['symbol']")


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock."""

    if request.method == "POST":
        symbol_field_entry = request.form.get("symbol")
        quantity_field_entry = request.form.get("quantity")

        print()
        print(symbol_field_entry)
        print(quantity_field_entry)
        print()

        if form_validated(symbol_field_entry, quantity_field_entry) == True:
            return proceed_with_purchase(symbol_field_entry, quantity_field_entry)
        else:
            return apology(form_validated(symbol_field_entry, quantity_field_entry))
    else:
        return render_template("buy.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        symbol_field_entry = request.form.get("symbol")
        quantity_field_entry = request.form.get("quantity")

        if form_validated(symbol_field_entry, quantity_field_entry) == True:
            return proceed_with_sale(symbol_field_entry, quantity_field_entry)
        else:
            return apology(form_validated(symbol_field_entry, quantity_field_entry))
    else:
        return render_template("sell.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions."""

    transaction_history = db.execute("SELECT * FROM transactions WHERE user_id = :user_id",\
    user_id = session['user_id'])

    return render_template("history.html",\
    transaction_history = transaction_history)
