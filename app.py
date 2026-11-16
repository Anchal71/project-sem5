
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date, timedelta
from functools import wraps

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-this-secret-key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///library.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="student")


class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(100))
    total_copies = db.Column(db.Integer, default=1)
    available_copies = db.Column(db.Integer, default=1)


class BookRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey("book.id"), nullable=False)
    status = db.Column(db.String(20), default="Pending")
    user = db.relationship("User")
    book = db.relationship("Book")


class BorrowedBook(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey("book.id"), nullable=False)
    issue_date = db.Column(db.Date, nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    returned_at = db.Column(db.Date, nullable=True)
    fine_amount = db.Column(db.Integer, default=0)
    user = db.relationship("User")
    book = db.relationship("Book")


def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.")
            return redirect(url_for("login"))
        return function(*args, **kwargs)
    return wrapper


def admin_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Admin access required.")
            return redirect(url_for("login"))
        return function(*args, **kwargs)
    return wrapper


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        if User.query.filter_by(email=email).first():
            flash("Email already registered.")
            return redirect(url_for("register"))

        user = User(
            username=username,
            email=email,
            password=generate_password_hash(password),
            role="student"
        )

        db.session.add(user)
        db.session.commit()

        flash("Registration successful. Please log in.")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        user = User.query.filter_by(email=email).first()
        print("USER FOUND:", user is not None)

        if user:
          print("PASSWORD MATCH:", check_password_hash(user.password, password))

        if user and check_password_hash(user.password, password):
            session["user_id"] = user.id
            session["username"] = user.username
            session["role"] = user.role

            if user.role == "admin":
                return redirect(url_for("admin_dashboard"))

            return redirect(url_for("student_dashboard"))

        flash("Invalid email or password.")

    return render_template("login.html")



@app.route("/student")
@login_required
def student_dashboard():
    if session.get("role") != "student":
        return redirect(url_for("admin_dashboard"))

    search = request.args.get("search", "").strip()

    books_query = Book.query

    if search:
        books_query = books_query.filter(
            Book.title.ilike(f"%{search}%") |
            Book.author.ilike(f"%{search}%") |
            Book.category.ilike(f"%{search}%")
        )

    books = books_query.order_by(Book.title).all()

    borrowed_books = BorrowedBook.query.filter_by(
        user_id=session["user_id"],
        returned_at=None
    ).all()
    borrowing_history = BorrowedBook.query.filter(
    BorrowedBook.user_id == session["user_id"],
    BorrowedBook.returned_at.isnot(None)
).order_by(BorrowedBook.returned_at.desc()).all()

    requests_list = BookRequest.query.filter_by(
        user_id=session["user_id"]
    ).order_by(BookRequest.id.desc()).all()

    return render_template(
        "student.html",
        books=books,
        borrowed_books=borrowed_books,
        borrowing_history=borrowing_history,
        requests_list=requests_list,
        today=date.today()
    )


@app.route("/request-book/<int:book_id>", methods=["POST"])
@login_required
def request_book(book_id):
    if session.get("role") != "student":
        return redirect(url_for("admin_dashboard"))

    book = db.session.get(Book, book_id)

    if not book:
        flash("Book not found.")
        return redirect(url_for("student_dashboard"))

    if book.available_copies <= 0:
        flash("This book is currently unavailable.")
        return redirect(url_for("student_dashboard"))

    existing = BookRequest.query.filter_by(
        user_id=session["user_id"],
        book_id=book_id,
        status="Pending"
    ).first()

    if existing:
        flash("You already have a pending request for this book.")
    else:
        new_request = BookRequest(
            user_id=session["user_id"],
            book_id=book_id
        )
        db.session.add(new_request)
        db.session.commit()
        flash("Book request submitted successfully.")

    return redirect(url_for("student_dashboard"))


@app.route("/admin")
@login_required
@admin_required
def admin_dashboard():
    books = Book.query.order_by(Book.title).all()

    pending_requests = BookRequest.query.filter_by(
        status="Pending"
    ).all()

    borrowed_books = BorrowedBook.query.filter_by(
        returned_at=None
    ).all()

    return render_template(
        "admin.html",
        books=books,
        pending_requests=pending_requests,
        borrowed_books=borrowed_books,
        today=date.today()
    )


@app.route("/add-book", methods=["POST"])
@login_required
@admin_required
def add_book():
    title = request.form["title"].strip()
    author = request.form["author"].strip()
    category = request.form["category"].strip()

    try:
        copies = int(request.form["copies"])
    except (ValueError, TypeError):
        copies = 0

    if not title or not author or copies < 1:
        flash("Enter valid book details and at least one copy.")
        return redirect(url_for("admin_dashboard"))

    book = Book(
        title=title,
        author=author,
        category=category,
        total_copies=copies,
        available_copies=copies
    )

    db.session.add(book)
    db.session.commit()

    flash("Book added successfully.")
    return redirect(url_for("admin_dashboard"))


@app.route("/approve-request/<int:request_id>", methods=["POST"])
@login_required
@admin_required
def approve_request(request_id):
    book_request = db.session.get(BookRequest, request_id)

    if not book_request or book_request.status != "Pending":
        flash("Request not found or already processed.")
        return redirect(url_for("admin_dashboard"))

    book = db.session.get(Book, book_request.book_id)

    if not book or book.available_copies < 1:
        flash("No copies are currently available.")
        return redirect(url_for("admin_dashboard"))

    borrowed = BorrowedBook(
        user_id=book_request.user_id,
        book_id=book.id,
        issue_date=date.today(),
        due_date=date.today() + timedelta(days=14)
    )

    book.available_copies -= 1
    book_request.status = "Approved"

    db.session.add(borrowed)
    db.session.commit()

    flash("Request approved and book issued.")
    return redirect(url_for("admin_dashboard"))


@app.route("/reject-request/<int:request_id>", methods=["POST"])
@login_required
@admin_required
def reject_request(request_id):
    book_request = db.session.get(BookRequest, request_id)

    if book_request and book_request.status == "Pending":
        book_request.status = "Rejected"
        db.session.commit()
        flash("Book request rejected.")

    return redirect(url_for("admin_dashboard"))


@app.route("/return-book/<int:borrow_id>", methods=["POST"])
@login_required
@admin_required
def return_book(borrow_id):
    borrowed = db.session.get(BorrowedBook, borrow_id)

    if not borrowed or borrowed.returned_at is not None:
        flash("Borrowing record not found or already returned.")
        return redirect(url_for("admin_dashboard"))

    today = date.today()
    overdue_days = max(0, (today - borrowed.due_date).days)

    borrowed.returned_at = today
    borrowed.fine_amount = overdue_days * 5

    book = db.session.get(Book, borrowed.book_id)
    book.available_copies += 1

    db.session.commit()

    flash(f"Book returned. Fine: Rs. {borrowed.fine_amount}")
    return redirect(url_for("admin_dashboard"))


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("home"))


with app.app_context():
    db.create_all()

    if not User.query.filter_by(role="admin").first():
        admin = User(
            username="Administrator",
            email="admin@library.com",
            password=generate_password_hash("Admin@123"),
            role="admin"
        )
        db.session.add(admin)
        db.session.commit()


if __name__ == "__main__":
    app.run(debug=True)
