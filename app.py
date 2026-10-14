import os
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect
from wtforms import StringField, PasswordField, SelectField, DecimalField, DateTimeLocalField, TextAreaField, IntegerField
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional, EqualTo
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import or_, func

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-this-secret-key")
database_url = os.environ.get("DATABASE_URL", "sqlite:///foodbridge.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
CSRFProtect(app)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message_category = "info"

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="donor")
    phone = db.Column(db.String(30))
    city = db.Column(db.String(100), nullable=False)
    is_approved = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Donation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    donor_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    food_name = db.Column(db.String(140), nullable=False)
    food_type = db.Column(db.String(60), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    quantity_unit = db.Column(db.String(20), nullable=False, default="servings")
    expiry_time = db.Column(db.DateTime, nullable=False, index=True)
    pickup_address = db.Column(db.String(240), nullable=False)
    city = db.Column(db.String(100), nullable=False, index=True)
    storage_notes = db.Column(db.String(240))
    status = db.Column(db.String(20), nullable=False, default="available", index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    claims = db.relationship("Claim", backref="donation", cascade="all, delete-orphan", lazy=True)
    donor = db.relationship("User", foreign_keys=[donor_id])

class Claim(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    donation_id = db.Column(db.Integer, db.ForeignKey("donation.id"), nullable=False, unique=True)
    claimer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    claimed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    picked_up_at = db.Column(db.DateTime)
    delivered_at = db.Column(db.DateTime)
    claimer = db.relationship("User", foreign_keys=[claimer_id])

class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    donation_id = db.Column(db.Integer, db.ForeignKey("donation.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

class RegisterForm(FlaskForm):
    name = StringField("Full name", validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=160)])
    phone = StringField("Phone (optional)", validators=[Optional(), Length(max=30)])
    city = StringField("City", validators=[DataRequired(), Length(max=100)])
    role = SelectField("Account type", choices=[("donor", "Food donor"), ("ngo", "NGO / volunteer")], validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8, message="Use at least 8 characters.")])
    confirm_password = PasswordField("Confirm password", validators=[DataRequired(), EqualTo("password", message="Passwords do not match.")])

class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])

class DonationForm(FlaskForm):
    food_name = StringField("Food name", validators=[DataRequired(), Length(max=140)])
    food_type = SelectField("Food category", choices=[
        ("Cooked meal", "Cooked meal"), ("Bakery", "Bakery"), ("Produce", "Fruits / vegetables"),
        ("Packaged", "Packaged food"), ("Groceries", "Groceries"), ("Other", "Other")
    ], validators=[DataRequired()])
    quantity = DecimalField("Quantity", places=2, validators=[DataRequired(), NumberRange(min=0.01, max=100000)])
    quantity_unit = SelectField("Unit", choices=[("servings", "servings"), ("kg", "kg"), ("packs", "packs"), ("boxes", "boxes")])
    expiry_time = DateTimeLocalField("Use-by / pickup deadline", format="%Y-%m-%dT%H:%M", validators=[DataRequired()])
    pickup_address = StringField("Pickup address", validators=[DataRequired(), Length(max=240)])
    city = StringField("City", validators=[DataRequired(), Length(max=100)])
    storage_notes = StringField("Storage / handling notes (optional)", validators=[Optional(), Length(max=240)])

class FeedbackForm(FlaskForm):
    rating = SelectField("Rating", choices=[("5","5 - Excellent"),("4","4 - Good"),("3","3 - Okay"),("2","2 - Poor"),("1","1 - Very poor")], validators=[DataRequired()])
    comment = TextAreaField("Comment (optional)", validators=[Optional(), Length(max=500)])

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def role_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            if current_user.role == "ngo" and not current_user.is_approved:
                flash("Your NGO / volunteer account is awaiting admin approval.", "warning")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)
        return wrapped
    return decorator

def update_expired_donations():
    now = datetime.utcnow()
    Donation.query.filter(Donation.status == "available", Donation.expiry_time <= now).update(
        {Donation.status: "expired"}, synchronize_session=False
    )
    db.session.commit()

@app.context_processor
def inject_helpers():
    return {"current_year": datetime.utcnow().year}

@app.route("/")
def home():
    update_expired_donations()
    counts = {
        "available": Donation.query.filter_by(status="available").count(),
        "delivered": Donation.query.filter_by(status="delivered").count(),
        "donors": User.query.filter_by(role="donor").count(),
        "partners": User.query.filter_by(role="ngo", is_approved=True).count()
    }
    latest = Donation.query.filter_by(status="available").order_by(Donation.created_at.desc()).limit(3).all()
    return render_template("home.html", counts=counts, latest=latest)

@app.route("/register", methods=["GET", "POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        if User.query.filter_by(email=email).first():
            flash("An account with this email already exists.", "danger")
            return render_template("register.html", form=form)
        role = form.role.data
        user = User(name=form.name.data.strip(), email=email, phone=form.phone.data.strip() if form.phone.data else None,
                    city=form.city.data.strip(), role=role, is_approved=(role == "donor"))
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash("Account created. NGO / volunteer accounts need admin approval before claiming donations." if role == "ngo" else "Account created. You can now sign in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html", form=form)

@app.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter(func.lower(User.email) == form.email.data.strip().lower()).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            flash("Welcome back!", "success")
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html", form=form)

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("home"))

@app.route("/dashboard")
@login_required
def dashboard():
    update_expired_donations()
    if current_user.role == "admin":
        return redirect(url_for("admin_dashboard"))
    if current_user.role == "donor":
        donations = Donation.query.filter_by(donor_id=current_user.id).order_by(Donation.created_at.desc()).all()
        return render_template("donor_dashboard.html", donations=donations)
    claims = Claim.query.filter_by(claimer_id=current_user.id).order_by(Claim.claimed_at.desc()).all()
    return render_template("claimer_dashboard.html", claims=claims)

@app.route("/donations")
def donations():
    update_expired_donations()
    city = request.args.get("city", "").strip()
    food_type = request.args.get("food_type", "").strip()
    query = Donation.query.filter_by(status="available").filter(Donation.expiry_time > datetime.utcnow())
    if city:
        query = query.filter(Donation.city.ilike(f"%{city}%"))
    if food_type:
        query = query.filter_by(food_type=food_type)
    results = query.order_by(Donation.expiry_time.asc()).all()
    return render_template("donations.html", donations=results, city=city, food_type=food_type)

@app.route("/donations/new", methods=["GET", "POST"])
@role_required("donor")
def new_donation():
    form = DonationForm()
    if form.validate_on_submit():
        expiry = form.expiry_time.data
        if expiry <= datetime.utcnow():
            flash("The use-by / pickup deadline must be in the future.", "danger")
            return render_template("donation_form.html", form=form, page_title="Post surplus food")
        donation = Donation(
            donor_id=current_user.id, food_name=form.food_name.data.strip(), food_type=form.food_type.data,
            quantity=float(form.quantity.data), quantity_unit=form.quantity_unit.data, expiry_time=expiry,
            pickup_address=form.pickup_address.data.strip(), city=form.city.data.strip(),
            storage_notes=form.storage_notes.data.strip() if form.storage_notes.data else None, status="available"
        )
        db.session.add(donation); db.session.commit()
        flash("Food listing published.", "success")
        return redirect(url_for("dashboard"))
    return render_template("donation_form.html", form=form, page_title="Post surplus food")

@app.route("/donations/<int:donation_id>/edit", methods=["GET", "POST"])
@role_required("donor")
def edit_donation(donation_id):
    donation = db.get_or_404(Donation, donation_id)
    if donation.donor_id != current_user.id or donation.status != "available":
        abort(403)
    form = DonationForm(obj=donation)
    if request.method == "GET":
        form.expiry_time.data = donation.expiry_time
    if form.validate_on_submit():
        expiry = form.expiry_time.data
        if expiry <= datetime.utcnow():
            flash("The deadline must be in the future.", "danger")
            return render_template("donation_form.html", form=form, page_title="Edit food listing")
        for field in ["food_name","food_type","quantity_unit","pickup_address","city","storage_notes"]:
            setattr(donation, field, getattr(form, field).data)
        donation.quantity = float(form.quantity.data)
        donation.expiry_time = expiry
        db.session.commit()
        flash("Listing updated.", "success")
        return redirect(url_for("dashboard"))
    return render_template("donation_form.html", form=form, page_title="Edit food listing")

@app.route("/donations/<int:donation_id>/cancel", methods=["POST"])
@role_required("donor")
def cancel_donation(donation_id):
    donation = db.get_or_404(Donation, donation_id)
    if donation.donor_id != current_user.id or donation.status != "available":
        abort(403)
    donation.status = "cancelled"
    db.session.commit()
    flash("Listing cancelled.", "info")
    return redirect(url_for("dashboard"))

@app.route("/donations/<int:donation_id>/claim", methods=["POST"])
@role_required("ngo")
def claim_donation(donation_id):
    donation = db.get_or_404(Donation, donation_id)
    if donation.status != "available" or donation.expiry_time <= datetime.utcnow():
        flash("This listing is no longer available.", "warning")
        return redirect(url_for("donations"))
    existing = Claim.query.filter_by(donation_id=donation.id).first()
    if existing:
        flash("This donation has already been claimed.", "warning")
        return redirect(url_for("donations"))
    claim = Claim(donation_id=donation.id, claimer_id=current_user.id)
    donation.status = "claimed"
    db.session.add(claim); db.session.commit()
    flash("Donation claimed. Contact the donor to coordinate pickup.", "success")
    return redirect(url_for("dashboard"))

@app.route("/claims/<int:claim_id>/status", methods=["POST"])
@role_required("ngo")
def update_claim_status(claim_id):
    claim = db.get_or_404(Claim, claim_id)
    if claim.claimer_id != current_user.id:
        abort(403)
    action = request.form.get("action")
    if action == "picked_up" and claim.donation.status == "claimed":
        claim.donation.status = "picked_up"; claim.picked_up_at = datetime.utcnow()
    elif action == "delivered" and claim.donation.status == "picked_up":
        claim.donation.status = "delivered"; claim.delivered_at = datetime.utcnow()
    else:
        flash("That status transition is not allowed.", "danger")
        return redirect(url_for("dashboard"))
    db.session.commit()
    flash("Donation status updated.", "success")
    return redirect(url_for("dashboard"))

@app.route("/claims/<int:claim_id>/feedback", methods=["GET", "POST"])
@login_required
def feedback(claim_id):
    claim = db.get_or_404(Claim, claim_id)
    if claim.donation.status != "delivered" or current_user.id not in [claim.claimer_id, claim.donation.donor_id]:
        abort(403)
    form = FeedbackForm()
    if form.validate_on_submit():
        existing = Feedback.query.filter_by(donation_id=claim.donation_id, user_id=current_user.id).first()
        if existing:
            flash("You have already submitted feedback for this donation.", "info")
        else:
            db.session.add(Feedback(donation_id=claim.donation_id, user_id=current_user.id,
                                    rating=int(form.rating.data), comment=form.comment.data or None))
            db.session.commit()
            flash("Thank you for your feedback.", "success")
        return redirect(url_for("dashboard"))
    return render_template("feedback.html", form=form, claim=claim)

@app.route("/admin")
@role_required("admin")
def admin_dashboard():
    update_expired_donations()
    users = User.query.order_by(User.created_at.desc()).all()
    recent = Donation.query.order_by(Donation.created_at.desc()).limit(8).all()
    status_counts = {status: Donation.query.filter_by(status=status).count()
                     for status in ["available","claimed","picked_up","delivered","expired","cancelled"]}
    totals = {
        "donations": Donation.query.count(),
        "delivered": status_counts["delivered"],
        "food_quantity": db.session.query(func.coalesce(func.sum(Donation.quantity), 0)).filter_by(status="delivered").scalar() or 0,
        "donors": User.query.filter_by(role="donor").count(),
        "pending_ngos": User.query.filter_by(role="ngo", is_approved=False).count()
    }
    return render_template("admin_dashboard.html", users=users, recent=recent, status_counts=status_counts, totals=totals)

@app.route("/admin/users/<int:user_id>/approve", methods=["POST"])
@role_required("admin")
def approve_user(user_id):
    user = db.get_or_404(User, user_id)
    if user.role != "ngo":
        abort(400)
    user.is_approved = True
    db.session.commit()
    flash(f"{user.name} is now approved.", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/users/<int:user_id>/revoke", methods=["POST"])
@role_required("admin")
def revoke_user(user_id):
    user = db.get_or_404(User, user_id)
    if user.role != "ngo":
        abort(400)
    user.is_approved = False
    db.session.commit()
    flash(f"Approval revoked for {user.name}.", "info")
    return redirect(url_for("admin_dashboard"))

@app.route("/about")
def about():
    return render_template("about.html")

@app.errorhandler(403)
def forbidden(_):
    return render_template("error.html", code=403, message="You do not have permission to access this page."), 403

@app.errorhandler(404)
def not_found(_):
    return render_template("error.html", code=404, message="The page you requested was not found."), 404

def init_database():
    with app.app_context():
        db.create_all()
        admin_email = os.environ.get("ADMIN_EMAIL")
        admin_password = os.environ.get("ADMIN_PASSWORD")
        if admin_email and admin_password and not User.query.filter_by(email=admin_email.lower()).first():
            admin = User(name=os.environ.get("ADMIN_NAME", "FoodBridge Admin"),
                         email=admin_email.lower(), city=os.environ.get("ADMIN_CITY", "Admin"),
                         role="admin", is_approved=True)
            admin.set_password(admin_password)
            db.session.add(admin)
            db.session.commit()

init_database()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
