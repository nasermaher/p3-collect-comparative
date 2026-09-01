s = "string"

t = [ord(s0) for s0 in s]

# for i in range(1632, 1642, 1):
#     print(i)
v = [chr(t0-10) for t0 in t]
print(chr(ord('\ufffc')), ord('\ufffc'))
print("ف", ord("ف"))
print(t, v)

# chr_ord = []
# for i in range(0, 65536):
#     chr_ord.append((i, chr(i)))
# print(chr_ord)
