import os, sqlite3, csv, io
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response
from werkzeug.security import generate_password_hash, check_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('DATABASE_PATH', os.path.join(BASE, 'data', 'rickshawparts.db'))
SECRET = os.environ.get('SECRET_KEY', 'change-this-secret-before-deployment')
app = Flask(__name__)
app.secret_key = SECRET
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

SCHEMA = '''
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT NOT NULL, role TEXT DEFAULT 'admin');
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, sku TEXT UNIQUE, name TEXT NOT NULL, category TEXT, vehicle_type TEXT, description TEXT, price REAL NOT NULL DEFAULT 0, cost REAL NOT NULL DEFAULT 0, stock INTEGER NOT NULL DEFAULT 0, reorder_level INTEGER NOT NULL DEFAULT 5, image_url TEXT, active INTEGER DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS customers(id INTEGER PRIMARY KEY, name TEXT NOT NULL, phone TEXT, address TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, customer_id INTEGER, customer_name TEXT, phone TEXT, address TEXT, total REAL NOT NULL, payment_method TEXT, payment_status TEXT DEFAULT 'Pending', status TEXT DEFAULT 'New', created_at TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(customer_id) REFERENCES customers(id));
CREATE TABLE IF NOT EXISTS order_items(id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER, product_name TEXT, quantity INTEGER, unit_price REAL, FOREIGN KEY(order_id) REFERENCES orders(id));
CREATE TABLE IF NOT EXISTS stock_movements(id INTEGER PRIMARY KEY, product_id INTEGER, movement TEXT, quantity INTEGER, note TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
'''
def db():
    con=sqlite3.connect(DB_PATH); con.row_factory=sqlite3.Row; return con

def init_db():
    con=db(); con.executescript(SCHEMA)
    if not con.execute('SELECT id FROM users WHERE username=?',('admin',)).fetchone():
        con.execute('INSERT INTO users(username,password_hash,role) VALUES(?,?,?)',('admin',generate_password_hash(os.environ.get('ADMIN_PASSWORD','Admin@12345')),'admin'))
    if con.execute('SELECT COUNT(*) FROM products').fetchone()[0] == 0:
        samples=[('RP-001','70cc Piston Kit','Engine','Petrol','Complete piston kit for 70cc rickshaw',1850,1320,18,5),('RP-002','Rickshaw Clutch Plate','Clutch','Petrol','Heavy-duty clutch plate',1250,850,12,4),('RP-003','Crankshaft Assembly','Engine','Petrol','Standard crankshaft assembly',6200,4850,4,3),('RP-004','CNG Kit Pipe','Fuel System','CNG','High-pressure compatible pipe',950,610,22,6),('RP-005','LED Headlight','Electrical','Electric','12V LED headlight',1450,900,9,4),('RP-006','Brake Shoe Set','Brakes','All','Front/rear brake shoe set',780,490,30,8),('RP-007','Gasket Set','Engine','All','Full engine gasket set',650,380,16,5),('RP-008','EV Controller','Electrical','Electric','Electric rickshaw controller',14500,11200,2,2)]
        con.executemany('INSERT INTO products(sku,name,category,vehicle_type,description,price,cost,stock,reorder_level) VALUES(?,?,?,?,?,?,?,?,?)',samples)
    con.commit(); con.close()
init_db()

def admin_required(fn):
    @wraps(fn)
    def wrapper(*a,**kw):
        if not session.get('admin_id'): return redirect(url_for('login', next=request.path))
        return fn(*a,**kw)
    return wrapper

@app.context_processor
def common(): return {'cart_count':sum(int(x) for x in session.get('cart',{}).values()),'money':lambda n: f'Rs. {float(n):,.0f}'}

@app.route('/')
def home():
    con=db(); products=con.execute('SELECT * FROM products WHERE active=1 ORDER BY id DESC LIMIT 8').fetchall(); categories=con.execute('SELECT DISTINCT category FROM products WHERE active=1 AND category IS NOT NULL').fetchall(); con.close()
    return render_template('home.html',products=products,categories=categories)

@app.route('/shop')
def shop():
    q=request.args.get('q','').strip(); category=request.args.get('category',''); vehicle=request.args.get('vehicle','')
    sql='SELECT * FROM products WHERE active=1'; args=[]
    if q: sql+=' AND (name LIKE ? OR sku LIKE ? OR description LIKE ?)'; args += [f'%{q}%']*3
    if category: sql+=' AND category=?'; args.append(category)
    if vehicle: sql+=' AND (vehicle_type=? OR vehicle_type="All")'; args.append(vehicle)
    sql+=' ORDER BY name'; con=db(); products=con.execute(sql,args).fetchall(); categories=con.execute('SELECT DISTINCT category FROM products WHERE active=1').fetchall(); con.close()
    return render_template('shop.html',products=products,categories=categories,q=q,category=category,vehicle=vehicle)

@app.route('/product/<int:pid>')
def product(pid):
    con=db(); p=con.execute('SELECT * FROM products WHERE id=? AND active=1',(pid,)).fetchone(); con.close()
    if not p: return 'Product not found',404
    return render_template('product.html',p=p)

@app.post('/cart/add/<int:pid>')
def add_cart(pid):
    con=db(); p=con.execute('SELECT id,stock FROM products WHERE id=? AND active=1',(pid,)).fetchone(); con.close()
    if not p: flash('Product unavailable.','error')
    else:
        cart=session.get('cart',{}); key=str(pid); qty=int(request.form.get('quantity',1)); cart[key]=min(int(cart.get(key,0))+max(1,qty),p['stock']); session['cart']=cart; flash('Added to cart.','success')
    return redirect(request.referrer or url_for('shop'))

@app.route('/cart')
def cart():
    cart=session.get('cart',{}); items=[]; total=0; con=db()
    for pid,qty in cart.items():
        p=con.execute('SELECT * FROM products WHERE id=? AND active=1',(int(pid),)).fetchone()
        if p:
            q=min(int(qty),p['stock']); subtotal=q*p['price']; total+=subtotal; items.append({'product':p,'quantity':q,'subtotal':subtotal})
    con.close(); return render_template('cart.html',items=items,total=total)

@app.post('/cart/update')
def update_cart():
    cart=session.get('cart',{})
    for pid,qty in request.form.items():
        if pid.isdigit():
            try: q=int(qty)
            except ValueError: q=0
            if q<=0: cart.pop(pid,None)
            else: cart[pid]=q
    session['cart']=cart; return redirect(url_for('cart'))

@app.route('/checkout',methods=['GET','POST'])
def checkout():
    cart=session.get('cart',{})
    if not cart: return redirect(url_for('shop'))
    if request.method=='POST':
        name=request.form.get('name','').strip(); phone=request.form.get('phone','').strip(); address=request.form.get('address','').strip(); method=request.form.get('payment_method','Cash on Delivery')
        if not name or not phone or not address: flash('Please complete all delivery details.','error'); return redirect(url_for('checkout'))
        con=db(); items=[]; total=0
        for pid,qty in cart.items():
            p=con.execute('SELECT * FROM products WHERE id=? AND active=1',(int(pid),)).fetchone(); q=int(qty)
            if not p or p['stock']<q: con.close(); flash('Stock changed. Please update your cart.','error'); return redirect(url_for('cart'))
            items.append((p,q)); total+=p['price']*q
        cur=con.execute('INSERT INTO customers(name,phone,address) VALUES(?,?,?)',(name,phone,address)); cid=cur.lastrowid
        cur=con.execute('INSERT INTO orders(customer_id,customer_name,phone,address,total,payment_method) VALUES(?,?,?,?,?,?)',(cid,name,phone,address,total,method)); oid=cur.lastrowid
        for p,q in items:
            con.execute('INSERT INTO order_items(order_id,product_id,product_name,quantity,unit_price) VALUES(?,?,?,?,?)',(oid,p['id'],p['name'],q,p['price']))
            con.execute('UPDATE products SET stock=stock-? WHERE id=?',(q,p['id']))
            con.execute('INSERT INTO stock_movements(product_id,movement,quantity,note) VALUES(?,?,?,?)',(p['id'],'OUT',q,f'Order #{oid}'))
        con.commit(); con.close(); session['cart']={}; return render_template('success.html',order_id=oid,total=total)
    return render_template('checkout.html')

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        con=db(); u=con.execute('SELECT * FROM users WHERE username=?',(request.form.get('username',''),)).fetchone(); con.close()
        if u and check_password_hash(u['password_hash'],request.form.get('password','')): session['admin_id']=u['id']; return redirect(request.args.get('next') or url_for('admin'))
        flash('Invalid username or password.','error')
    return render_template('login.html')
@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('home'))

@app.route('/admin')
@admin_required
def admin():
    con=db(); kpis={'products':con.execute('SELECT COUNT(*) FROM products WHERE active=1').fetchone()[0],'stock':con.execute('SELECT COALESCE(SUM(stock),0) FROM products WHERE active=1').fetchone()[0],'low':con.execute('SELECT COUNT(*) FROM products WHERE active=1 AND stock<=reorder_level').fetchone()[0],'orders':con.execute('SELECT COUNT(*) FROM orders').fetchone()[0],'sales':con.execute("SELECT COALESCE(SUM(total),0) FROM orders WHERE status!='Cancelled'").fetchone()[0]}; recent=con.execute('SELECT * FROM orders ORDER BY id DESC LIMIT 8').fetchall(); low=con.execute('SELECT * FROM products WHERE active=1 AND stock<=reorder_level ORDER BY stock').fetchall(); con.close()
    return render_template('admin.html',kpis=kpis,recent=recent,low=low)

@app.route('/admin/products',methods=['GET','POST'])
@admin_required
def admin_products():
    con=db()
    if request.method=='POST':
        f=request.form
        try: con.execute('INSERT INTO products(sku,name,category,vehicle_type,description,price,cost,stock,reorder_level) VALUES(?,?,?,?,?,?,?,?,?)',(f['sku'],f['name'],f.get('category'),f.get('vehicle_type','All'),f.get('description',''),float(f['price']),float(f.get('cost') or 0),int(f['stock']),int(f.get('reorder_level') or 5))); con.commit(); flash('Product added.','success')
        except sqlite3.IntegrityError: flash('SKU already exists.','error')
        return redirect(url_for('admin_products'))
    products=con.execute('SELECT * FROM products ORDER BY active DESC,name').fetchall(); con.close(); return render_template('admin_products.html',products=products)

@app.post('/admin/product/<int:pid>/stock')
@admin_required
def stock_adjust(pid):
    try: qty=int(request.form.get('quantity',0))
    except ValueError: qty=0
    movement=request.form.get('movement','IN'); delta=qty if movement=='IN' else -qty
    con=db(); p=con.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone()
    if p and qty>0 and p['stock']+delta>=0:
        con.execute('UPDATE products SET stock=stock+? WHERE id=?',(delta,pid)); con.execute('INSERT INTO stock_movements(product_id,movement,quantity,note) VALUES(?,?,?,?)',(pid,movement,qty,request.form.get('note','Manual adjustment'))); con.commit(); flash('Stock updated.','success')
    else: flash('Invalid stock adjustment.','error')
    con.close(); return redirect(url_for('admin_products'))

@app.post('/admin/product/<int:pid>/archive')
@admin_required
def archive_product(pid):
    con=db(); con.execute('UPDATE products SET active=0 WHERE id=?',(pid,)); con.commit(); con.close(); flash('Product archived.','success'); return redirect(url_for('admin_products'))

@app.route('/admin/orders')
@admin_required
def admin_orders():
    con=db(); orders=con.execute('SELECT * FROM orders ORDER BY id DESC').fetchall(); con.close(); return render_template('admin_orders.html',orders=orders)
@app.post('/admin/order/<int:oid>/update')
@admin_required
def update_order(oid):
    con=db(); con.execute('UPDATE orders SET status=?,payment_status=? WHERE id=?',(request.form.get('status','New'),request.form.get('payment_status','Pending'),oid)); con.commit(); con.close(); flash('Order updated.','success'); return redirect(url_for('admin_orders'))

@app.route('/admin/reports')
@admin_required
def reports():
    con=db(); rows=con.execute("SELECT date(created_at) day,COUNT(*) orders,SUM(total) sales FROM orders WHERE status!='Cancelled' GROUP BY date(created_at) ORDER BY day DESC LIMIT 30").fetchall(); profit=con.execute("SELECT COALESCE(SUM((oi.unit_price-p.cost)*oi.quantity),0) FROM order_items oi JOIN products p ON p.id=oi.product_id JOIN orders o ON o.id=oi.order_id WHERE o.status!='Cancelled'").fetchone()[0]; con.close(); return render_template('reports.html',rows=rows,profit=profit)
@app.route('/admin/export/products.csv')
@admin_required
def export_products():
    con=db(); rows=con.execute('SELECT sku,name,category,vehicle_type,price,cost,stock,reorder_level FROM products WHERE active=1').fetchall(); con.close(); out=io.StringIO(); w=csv.writer(out); w.writerow(['SKU','Name','Category','Vehicle','Price PKR','Cost PKR','Stock','Reorder Level']); w.writerows([tuple(r) for r in rows]); return Response(out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=rickshawparts-products.csv'})
@app.route('/health')
def health(): return jsonify(status='ok',app='RickshawParts Pro')

if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)),debug=False)
