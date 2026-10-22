import os
import random
import io
import json
from datetime import timedelta, datetime, timezone
import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TOKEN")

# ---------------- AYARLAR ----------------
PREFIX = "."
SUSTURMA_ROLU = "Susturulmuş"
DGKO_ROL_ID = 1401175152259104778
DGKO_KAYIT_DOSYASI = "dgko_zamanli_roller.json"
TURKIYE_SAATI = timezone(timedelta(hours=3), "Türkiye Saati")

# Görsel linkleri: tırnakların içine .png / .jpg / .gif ile biten doğrudan link yapıştır.
# Boş bırakırsan o komut görselsiz çalışır.
GORSELLER = {
    "kick": "",
    "ban": "",
    "infaz": "",
}

FAZIL_GORSEL = "https://media.discordapp.net/stickers/1080184403315146883.webp?size=160&quality=lossless"


def gorsel_ekle(embed, anahtar):
    url = GORSELLER.get(anahtar)
    if url:
        embed.set_image(url=url)
    return embed


def ses_yetkisi():
    """Üyeleri Sustur iznini sunucu (rol) düzeyinde kontrol eder.
    Not: commands.has_permissions yazı kanalında ses izinlerini göremez, bu yüzden özel kontrol."""
    async def predicate(ctx):
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        if not ctx.author.guild_permissions.mute_members:
            raise commands.MissingPermissions(["mute_members"])
        if not ctx.guild.me.guild_permissions.mute_members:
            raise commands.BotMissingPermissions(["mute_members"])
        return True
    return commands.check(predicate)


intents = discord.Intents.default()
intents.message_content = True  # Mesajları okumak için
intents.members = True          # Üye bulma ve üye bilgileri için
intents.presences = True        # Spotify etkinliğini okuyabilmek için

bot = commands.Bot(
    command_prefix=PREFIX,
    intents=intents,
    help_command=None,
    case_insensitive=True,
)


# ---------------- OLAYLAR ----------------
@bot.event
async def on_ready():
    print(f"{bot.user} olarak giriş yapıldı!")
    await bot.change_presence(activity=discord.Game(name=f"{PREFIX}imdat"))
    if not dgko_rol_kontrol.is_running():
        dgko_rol_kontrol.start()


def dgko_kayitlarini_oku():
    try:
        with open(DGKO_KAYIT_DOSYASI, "r", encoding="utf-8") as dosya:
            veriler = json.load(dosya)
            return veriler if isinstance(veriler, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def dgko_kayitlarini_yaz(veriler):
    with open(DGKO_KAYIT_DOSYASI, "w", encoding="utf-8") as dosya:
        json.dump(veriler, dosya, ensure_ascii=False, indent=2)


@tasks.loop(seconds=30)
async def dgko_rol_kontrol():
    """DGKO ile geçici verilen rolleri Türkiye saatine göre gece yarısında kaldırır."""
    kayitlar = dgko_kayitlarini_oku()
    if not kayitlar:
        return

    simdi = datetime.now(TURKIYE_SAATI)
    kalan = []
    degisti = False
    for kayit in kayitlar:
        try:
            kaldirma_zamani = datetime.fromisoformat(kayit["kaldirma_zamani"])
            if kaldirma_zamani.tzinfo is None:
                kaldirma_zamani = kaldirma_zamani.replace(tzinfo=TURKIYE_SAATI)
            if simdi < kaldirma_zamani:
                kalan.append(kayit)
                continue

            guild = bot.get_guild(int(kayit["guild_id"]))
            if guild is None:
                # Sunucu geçici olarak bulunamıyorsa kaydı sonraki kontrol için sakla.
                kalan.append(kayit)
                continue
            member = guild.get_member(int(kayit["member_id"]))
            role = guild.get_role(int(kayit["role_id"]))
            if member is not None and role is not None and role in member.roles:
                await member.remove_roles(role, reason=".dgko ile verilen geçici rolün gece yarısında kaldırılması")
            degisti = True
        except (KeyError, ValueError, TypeError) as exc:
            print(f"DGKO rol kaydı okunamadı: {exc}")
            degisti = True
        except discord.Forbidden:
            print("DGKO rolü kaldırılamadı: botun rol hiyerarşisini ve Rolleri Yönet iznini kontrol et.")
            kalan.append(kayit)
        except discord.HTTPException as exc:
            print(f"DGKO rolü kaldırılırken Discord hatası oluştu: {exc}")
            kalan.append(kayit)

    if degisti or len(kalan) != len(kayitlar):
        dgko_kayitlarini_yaz(kalan)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Bu komutu kullanmak için yetkin yok.")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send("❌ Bu işlem için botun yetkisi yok. Bota gerekli izni ver.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Eksik bilgi girdin. Örnek kullanım için `{PREFIX}imdat` yaz.")
    elif isinstance(error, (commands.MemberNotFound, commands.UserNotFound)):
        await ctx.send("❌ Kullanıcı bulunamadı.")
    elif isinstance(error, commands.RoleNotFound):
        await ctx.send("❌ Rol bulunamadı.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Girdiğin değer geçersiz.")
    elif isinstance(error, commands.NoPrivateMessage):
        await ctx.send("❌ Bu komut sadece sunucuda kullanılabilir.")
    else:
        print(f"Hata: {error}")
        await ctx.send("❌ Bir hata oluştu.")


# ---------------- GENEL ----------------
@bot.command(aliases=["yardım", "yardim", "help"])
async def imdat(ctx):
    embed = discord.Embed(
        title="📖 Komut Listesi",
        description="Değişen komutlar **yeni = eski** şeklinde gösterilir.",
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="🛡️ Moderasyon",
        value=f"`{PREFIX}yolal = {PREFIX}kick` → `{PREFIX}yolal @kişi [sebep]`\n"
              f"`{PREFIX}idamet = {PREFIX}ban` → `{PREFIX}idamet @kişi [sebep]`\n"
              f"`{PREFIX}infazet = {PREFIX}forceban` → `{PREFIX}infazet kullanıcı_id [sebep]`\n"
              f"`{PREFIX}dirilt = {PREFIX}unban` → `{PREFIX}dirilt kullanıcı_id`\n"
              f"`{PREFIX}klavyesinikır = {PREFIX}chatmute` → `{PREFIX}klavyesinikır @kişi [sebep]`\n"
              f"`{PREFIX}ağzınaver = {PREFIX}voicemute` → `{PREFIX}ağzınaver @kişi [sebep]`\n"
              f"`{PREFIX}ağzındançıkart = {PREFIX}unvoicemute` → `{PREFIX}ağzındançıkart @kişi`\n"
              f"`{PREFIX}molapaspası = {PREFIX}timeout` → `{PREFIX}molapaspası @kişi [dakika] [sebep]`\n"
              f"`{PREFIX}sil sayı`",
        inline=False,
    )
    embed.add_field(
        name="🎭 Roller",
        value=f"`{PREFIX}rolver @kişi rol`\n`{PREFIX}rolal @kişi rol`",
        inline=False,
    )
    embed.add_field(
        name="🎲 Eğlence",
        value=f"`{PREFIX}zar [kenar]`\n`{PREFIX}yazitura`\n`{PREFIX}espri`\n`{PREFIX}sorusor soru`\n"
              f"`{PREFIX}fazılınanası`\n`{PREFIX}patlat [@kişi]`",
        inline=False,
    )
    embed.add_field(
        name="ℹ️ Bilgi",
        value=f"`{PREFIX}kullanici [@kişi]`\n`{PREFIX}sunucu`\n`{PREFIX}avatar [@kişi]`\n`{PREFIX}ping`",
        inline=False,
    )
    embed.add_field(
        name="📌 Genel",
        value=f"`{PREFIX}imdat = {PREFIX}yardım` → bu listeyi gösterir\n`{PREFIX}merhaba`",
        inline=False,
    )
    embed.add_field(
        name="🎵 Spotify",
        value=f"`{PREFIX}sp` / `{PREFIX}spo` / `{PREFIX}spotify` → dinlenen şarkıyı görsel kart olarak gönderir",
        inline=False,
    )
    embed.add_field(
        name="💘 Ship",
        value=f"`{PREFIX}ship @kişi` → sen ve seçtiğin kişi\n`{PREFIX}ship` → rastgele iki üye\n`{PREFIX}shipgununçifti` → günün çifti (her gün değişir)",
        inline=False,
    )
    embed.add_field(
        name="💍 Evlilik",
        value=f"`{PREFIX}evlen @kişi` → evlilik teklifi gönderir\n`{PREFIX}boşan` → evliliğini bitirir\n`{PREFIX}evlilik [@kişi]` → evlilik durumunu gösterir",
        inline=False,
    )
    await ctx.send(embed=embed)


@bot.command()
async def merhaba(ctx):
    await ctx.send(f"Merhaba {ctx.author.mention}!")


@bot.command()
async def ping(ctx):
    await ctx.send(f"🏓 Pong! {round(bot.latency * 1000)} ms")


# ---------------- MODERASYON ----------------
@bot.command(aliases=["kick"])
@commands.guild_only()
@commands.has_permissions(kick_members=True)
@commands.bot_has_permissions(kick_members=True)
async def yolal(ctx, member: discord.Member, *, sebep: str = "Sebep belirtilmedi"):
    if member == ctx.author:
        return await ctx.send("❌ Kendini atamazsın.")
    try:
        await member.kick(reason=f"{ctx.author}: {sebep}")
        embed = discord.Embed(
            title="👢 Üye Atıldı",
            description=f"**{member}** sunucudan atıldı.\nSebep: {sebep}",
            color=discord.Color.orange(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=gorsel_ekle(embed, "kick"))
    except discord.Forbidden:
        await ctx.send("❌ Bu kişiyi atamıyorum (rolü benden yüksek olabilir).")


@bot.command(aliases=["ban"])
@commands.guild_only()
@commands.has_permissions(ban_members=True)
@commands.bot_has_permissions(ban_members=True)
async def idamet(ctx, member: discord.Member, *, sebep: str = "Sebep belirtilmedi"):
    if member == ctx.author:
        return await ctx.send("❌ Kendini banlayamazsın.")
    try:
        await member.ban(reason=f"{ctx.author}: {sebep}")
        embed = discord.Embed(
            title="🔨 Üye Banlandı",
            description=f"**{member}** sunucudan banlandı.\nSebep: {sebep}",
            color=discord.Color.red(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=gorsel_ekle(embed, "ban"))
    except discord.Forbidden:
        await ctx.send("❌ Bu kişiyi banlayamıyorum (rolü benden yüksek olabilir).")


@bot.command(aliases=["forceban"])
@commands.guild_only()
@commands.has_permissions(ban_members=True)
@commands.bot_has_permissions(ban_members=True)
async def infazet(ctx, kullanici_id: int, *, sebep: str = "Sebep belirtilmedi"):
    """Sunucuda olmayan kişiyi de ID ile banlar."""
    if kullanici_id == ctx.author.id:
        return await ctx.send("❌ Kendini banlayamazsın.")
    if kullanici_id == bot.user.id:
        return await ctx.send("❌ Kendimi banlayamam.")
    if kullanici_id == ctx.guild.owner_id:
        return await ctx.send("❌ Sunucu sahibini banlayamazsın.")

    try:
        kullanici = await bot.fetch_user(kullanici_id)
    except discord.NotFound:
        return await ctx.send("❌ Bu ID'ye sahip bir Discord kullanıcısı bulunamadı.")

    try:
        await ctx.guild.ban(kullanici, reason=f"{ctx.author} (infaz): {sebep}")
        embed = discord.Embed(
            title="⚖️ İnfaz Edildi",
            description=f"**{kullanici}** (`{kullanici.id}`)\nSebep: {sebep}",
            color=discord.Color.dark_red(),
        )
        embed.set_thumbnail(url=kullanici.display_avatar.url)
        await ctx.send(embed=gorsel_ekle(embed, "infaz"))
    except discord.Forbidden:
        await ctx.send("❌ Bu kişiyi banlayamıyorum (rolü benden yüksek olabilir).")


@bot.command(aliases=["unban"])
@commands.guild_only()
@commands.has_permissions(ban_members=True)
@commands.bot_has_permissions(ban_members=True)
async def dirilt(ctx, kullanici_id: int):
    try:
        kullanici = await bot.fetch_user(kullanici_id)
        await ctx.guild.unban(kullanici)
        await ctx.send(f"✅ {kullanici} kullanıcısının banı kaldırıldı.")
    except discord.NotFound:
        await ctx.send("❌ Bu ID'ye sahip banlı bir kullanıcı bulunamadı.")


@bot.command(name="ağzınaver", aliases=["agzinaver", "voicemute"])
@commands.guild_only()
@ses_yetkisi()
async def agzinaver(ctx, member: discord.Member, *, sebep: str = "Sebep belirtilmedi"):
    """Üyeyi sesli kanalda susturur (voicemute). Üye bir ses kanalında olmalı."""
    if member == ctx.author:
        return await ctx.send("❌ Kendini susturamazsın.")
    if member.voice is None or member.voice.channel is None:
        return await ctx.send("❌ Bu kişi şu an bir ses kanalında değil.")
    if member.voice.mute:
        return await ctx.send("❌ Bu kişi zaten sesli olarak susturulmuş.")
    try:
        await member.edit(mute=True, reason=f"{ctx.author} (voicemute): {sebep}")
        embed = discord.Embed(
            title="🎙️ Ağzına Verildi",
            description=f"{member.mention} ses kanalında susturuldu.\nSebep: {sebep}",
            color=discord.Color.dark_orange(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)
    except discord.Forbidden:
        await ctx.send("❌ Bu kişiyi susturamıyorum (rolü benden yüksek olabilir).")
    except discord.HTTPException:
        await ctx.send("❌ Susturma başarısız oldu. Kişi ses kanalından çıkmış olabilir.")


@bot.command(name="ağzındançıkart", aliases=["agzindancikart", "unvoicemute"])
@commands.guild_only()
@ses_yetkisi()
async def agzindancikart(ctx, member: discord.Member):
    """Üyenin ses susturmasını kaldırır (unvoicemute)."""
    if member.voice is None or member.voice.channel is None:
        return await ctx.send("❌ Bu kişi şu an bir ses kanalında değil.")
    if not member.voice.mute:
        return await ctx.send("❌ Bu kişi sesli olarak susturulmamış.")
    try:
        await member.edit(mute=False, reason=f"{ctx.author} (unvoicemute)")
        await ctx.send(f"🎙️ {member.mention} artık ses kanalında konuşabilir.")
    except discord.Forbidden:
        await ctx.send("❌ Bu kişinin susturmasını kaldıramıyorum (rolü benden yüksek olabilir).")
    except discord.HTTPException:
        await ctx.send("❌ İşlem başarısız oldu. Kişi ses kanalından çıkmış olabilir.")


@bot.command(name="klavyesinikır", aliases=["klavyesinikir", "chatmute"])
@commands.guild_only()
@commands.has_permissions(manage_roles=True)
@commands.bot_has_permissions(manage_roles=True, manage_channels=True)
async def klavyesinikir(ctx, member: discord.Member, *, sebep: str = "Sebep belirtilmedi"):
    """Üyenin yazı kanallarında mesaj yazmasını engeller (chatmute). Ses kanalına karışmaz."""
    if member == ctx.author:
        return await ctx.send("❌ Kendini susturamazsın.")

    rol = discord.utils.get(ctx.guild.roles, name=SUSTURMA_ROLU)
    if rol is not None and rol in member.roles:
        return await ctx.send("❌ Bu kişi zaten yazı olarak susturulmuş.")

    try:
        if rol is None:
            await ctx.send("⏳ İlk kullanım: susturma rolü hazırlanıyor, kanallar ayarlanıyor...")
            rol = await ctx.guild.create_role(name=SUSTURMA_ROLU, reason="chatmute rolü")

            # Rolün yazma izinlerini tüm kanallarda kapat
            for kanal in ctx.guild.channels:
                if isinstance(kanal, (discord.TextChannel, discord.ForumChannel, discord.CategoryChannel)):
                    await kanal.set_permissions(
                        rol,
                        send_messages=False,
                        send_messages_in_threads=False,
                        create_public_threads=False,
                        create_private_threads=False,
                        add_reactions=False,
                        reason="chatmute rolü",
                    )

        await member.add_roles(rol, reason=f"{ctx.author} (chatmute): {sebep}")
        embed = discord.Embed(
            title="⌨️ Klavyesi Kırıldı",
            description=f"{member.mention} artık yazı kanallarında mesaj yazamaz.\nSebep: {sebep}",
            color=discord.Color.dark_gold(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)
    except discord.Forbidden:
        await ctx.send("❌ İşlem yapılamadı. Botun rolü, susturulacak kişinin rolünün üstünde olmalı.")


@bot.command(name="molapaspası", aliases=["molapaspasi", "timeout"])
@commands.guild_only()
@commands.has_permissions(moderate_members=True)
@commands.bot_has_permissions(moderate_members=True)
async def molapaspasi(ctx, member: discord.Member, dakika: int = 5, *, sebep: str = "Sebep belirtilmedi"):
    """Üyeye kısa bir zaman aşımı (timeout) verir (varsayılan 5 dk, en fazla 28 gün)."""
    if member == ctx.author:
        return await ctx.send("❌ Kendine mola veremezsin.")
    if dakika < 1 or dakika > 40320:
        return await ctx.send("❌ Süre 1 ile 40320 dakika (28 gün) arasında olmalı.")
    try:
        await member.timeout(timedelta(minutes=dakika), reason=f"{ctx.author} (molapaspası): {sebep}")
        embed = discord.Embed(
            title="🧹 Mola Paspası",
            description=f"{member.mention} **{dakika} dakika** molaya gönderildi.\nSebep: {sebep}",
            color=discord.Color.gold(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)
    except discord.Forbidden:
        await ctx.send("❌ Bu kişiye zaman aşımı veremiyorum (rolü benden yüksek ya da yönetici olabilir).")


@bot.command(aliases=["temizle", "purge"])
@commands.guild_only()
@commands.has_permissions(manage_messages=True)
@commands.bot_has_permissions(manage_messages=True)
async def sil(ctx, sayi: int):
    if sayi < 1 or sayi > 100:
        return await ctx.send("❌ 1 ile 100 arasında bir sayı gir.")
    silinen = await ctx.channel.purge(limit=sayi + 1)  # +1: komut mesajının kendisi
    await ctx.send(f"🧹 {len(silinen) - 1} mesaj silindi.", delete_after=3)


# ---------------- ROLLER ----------------
@bot.command()
@commands.guild_only()
@commands.has_permissions(manage_roles=True)
@commands.bot_has_permissions(manage_roles=True)
async def rolver(ctx, member: discord.Member, *, rol: discord.Role):
    try:
        await member.add_roles(rol)
        await ctx.send(f"✅ {member.mention} kişisine **{rol.name}** rolü verildi.")
    except discord.Forbidden:
        await ctx.send("❌ Bu rolü veremiyorum. Botun rolü, vermek istediğin rolden üstte olmalı.")


@bot.command()
@commands.guild_only()
@commands.has_permissions(manage_roles=True)
@commands.bot_has_permissions(manage_roles=True)
async def rolal(ctx, member: discord.Member, *, rol: discord.Role):
    try:
        await member.remove_roles(rol)
        await ctx.send(f"✅ {member.mention} kişisinden **{rol.name}** rolü alındı.")
    except discord.Forbidden:
        await ctx.send("❌ Bu rolü alamıyorum. Botun rolü, almak istediğin rolden üstte olmalı.")


# ---------------- EĞLENCE ----------------
ESPRILER = [
    "Neden bilgisayar soğuk almaz? Çünkü Windows'u hep açıktır.",
    "Programcı markete gider: 'Bir ekmek al, yumurta varsa 6 tane al.' Eve 6 ekmekle döner.",
    "Bilgisayarım yavaşladı, ben de ona sabır paketi yükledim.",
    "Python'cu neden gözlük takmaz? Çünkü C'yi (Sharp) görmek ister.",
    "Hata değil, özellik!",
]

CEVAPLAR = [
    "Evet.", "Hayır.", "Kesinlikle!", "Pek sanmam.", "Belki.",
    "Şüpheliyim.", "Bence evet.", "Şimdi söylemesem daha iyi.",
]


@bot.command()
async def zar(ctx, kenar: int = 6):
    if kenar < 2 or kenar > 1000:
        return await ctx.send("❌ Kenar sayısı 2 ile 1000 arasında olmalı.")
    await ctx.send(f"🎲 {ctx.author.mention} zar attı: **{random.randint(1, kenar)}** (1-{kenar})")


@bot.command(aliases=["yazıtura", "yt"])
async def yazitura(ctx):
    await ctx.send(f"🪙 {random.choice(['Yazı', 'Tura'])}!")


@bot.command(name="fazılınanası", aliases=["fazilinanasi"])
async def fazilinanasi(ctx):
    embed = discord.Embed(color=discord.Color.blurple())
    embed.set_image(url=FAZIL_GORSEL)
    await ctx.send(embed=embed)


@bot.command(name="patlat")
async def patlat(ctx, member: discord.Member = None):
    if member:
        await ctx.send(f"{member.mention} anasının amını mı? 💥")
    else:
        await ctx.send("ananın amını mı? 💥")


@bot.command()
async def espri(ctx):
    await ctx.send(random.choice(ESPRILER))


@bot.command(aliases=["8ball"])
async def sorusor(ctx, *, soru: str):
    await ctx.send(f"🔮 **Soru:** {soru}\n**Cevap:** {random.choice(CEVAPLAR)}")


# ---------------- BİLGİ ----------------
@bot.command(aliases=["kullanıcı", "ben", "userinfo"])
@commands.guild_only()
async def kullanici(ctx, member: discord.Member = None):
    member = member or ctx.author
    roller = [r.mention for r in member.roles if r.name != "@everyone"]

    embed = discord.Embed(title=str(member), color=member.color)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ID", value=member.id, inline=False)
    embed.add_field(name="Hesap oluşturma", value=discord.utils.format_dt(member.created_at, "D"), inline=True)
    embed.add_field(name="Sunucuya katılma", value=discord.utils.format_dt(member.joined_at, "D"), inline=True)
    embed.add_field(name="Roller", value=" ".join(roller) if roller else "Rol yok", inline=False)
    await ctx.send(embed=embed)


@bot.command(aliases=["serverinfo"])
@commands.guild_only()
async def sunucu(ctx):
    g = ctx.guild
    embed = discord.Embed(title=g.name, color=discord.Color.blurple())
    if g.icon:
        embed.set_thumbnail(url=g.icon.url)
    embed.add_field(name="Sahip", value=g.owner.mention if g.owner else "Bilinmiyor", inline=True)
    embed.add_field(name="Üye sayısı", value=g.member_count, inline=True)
    embed.add_field(name="Kanal sayısı", value=len(g.channels), inline=True)
    embed.add_field(name="Rol sayısı", value=len(g.roles), inline=True)
    embed.add_field(name="Oluşturulma", value=discord.utils.format_dt(g.created_at, "D"), inline=True)
    await ctx.send(embed=embed)


@bot.command()
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"{member} avatarı", color=discord.Color.blurple())
    embed.set_image(url=member.display_avatar.url)
    await ctx.send(embed=embed)


# ---------------- SHIP SİSTEMİ ----------------
def kayitsiz_rolu_var(member: discord.Member) -> bool:
    """Kayıtsız rolü olan üyelerin ship sistemine katılmasını engeller."""
    for role in getattr(member, "roles", []):
        rol_adi = role.name.casefold().replace("ı", "i").strip()
        if "kayitsiz" in rol_adi:
            return True
    return False


def ship_yuzdesi(guild_id: int, user1_id: int, user2_id: int) -> int:
    """Her ship komutunda yeniden rastgele bir uyum yüzdesi üretir."""
    return random.randint(1, 100)


def ship_yorumu(yuzde: int) -> str:
    if yuzde >= 95:
        return "💍 Ruh eşleri! Düğün davetiyelerini hazırlayın."
    if yuzde >= 80:
        return "💕 Aranızda çok güçlü bir kıvılcım var!"
    if yuzde >= 60:
        return "💗 Güzel bir çift olabilirsiniz."
    if yuzde >= 40:
        return "💞 Biraz flört, biraz şans gerekiyor."
    if yuzde >= 20:
        return "💔 Zıt kutuplar mı, yoksa sadece arkadaş mı?"
    return "🫣 Bugün yıldızlar pek aynı hizaya gelmemiş."


async def ship_kart_olustur(member1: discord.Member, member2: discord.Member, yuzde: int):
    """İki üyenin avatarlarını romantik bir PNG ship kartına yerleştirir."""
    width, height = 1000, 420
    image = Image.new("RGB", (width, height), (35, 17, 35))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((12, 12, width - 12, height - 12), radius=28, fill=(62, 27, 53), outline=(255, 150, 190), width=3)

    # Hafif pembe kalp süsleri
    for x, y, r in [(500, 70, 18), (470, 340, 10), (540, 330, 13), (180, 70, 8), (820, 75, 11)]:
        draw.text((x-r, y-r), "♥", font=ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", max(16, r*2)) if os.name == "nt" else ImageFont.load_default(), fill=(255, 125, 175))

    async def get_avatar(member):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(member.display_avatar.replace(size=256, format="png").url, timeout=aiohttp.ClientTimeout(total=12)) as response:
                    if response.status == 200:
                        data = await response.read()
                        avatar = Image.open(io.BytesIO(data)).convert("RGBA").resize((190, 190), Image.Resampling.LANCZOS)
                        mask = Image.new("L", (190, 190), 0)
                        ImageDraw.Draw(mask).ellipse((0, 0, 189, 189), fill=255)
                        avatar.putalpha(mask)
                        return avatar
        except Exception as exc:
            print(f"Ship avatarı indirilemedi: {exc}")
        return None

    avatar1, avatar2 = await get_avatar(member1), await get_avatar(member2)
    for x, avatar in [(100, avatar1), (710, avatar2)]:
        draw.ellipse((x-5, 105, x+195, 305), fill=(255, 160, 195), outline=(255, 225, 235), width=4)
        if avatar:
            image.paste(avatar, (x, 110), avatar)
        else:
            draw.ellipse((x, 110, x+190, 300), fill=(120, 70, 100))

    def font(size, bold=False):
        paths = ([r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\arial.ttf"] if bold else [r"C:\Windows\Fonts\arial.ttf"])
        for path in paths:
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                pass
        return ImageFont.load_default()

    draw.text((500, 150), "♥", font=font(72, True), fill=(255, 95, 155), anchor="mm")
    draw.text((500, 215), f"{yuzde}%", font=font(52, True), fill=(255, 235, 245), anchor="mm")
    draw.text((500, 265), "UYUM", font=font(20, True), fill=(255, 185, 215), anchor="mm")
    name1 = member1.display_name[:18]
    name2 = member2.display_name[:18]
    draw.text((195, 325), name1, font=font(25, True), fill=(255, 240, 247), anchor="mm")
    draw.text((805, 325), name2, font=font(25, True), fill=(255, 240, 247), anchor="mm")
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    output.seek(0)
    return output


class ShipEvlilikTeklifiView(discord.ui.View):
    """%90 üzeri ship sonucunda komutu kullanan kişinin teklif göndermesini sağlar."""
    def __init__(self, teklif_eden: discord.Member, teklif_alabilecekler: list[discord.Member]):
        super().__init__(timeout=120)
        self.teklif_eden = teklif_eden
        self.teklif_alabilecekler = teklif_alabilecekler

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.teklif_eden.id:
            await interaction.response.send_message(
                f"💌 Bu butonu yalnızca {self.teklif_eden.mention} kullanabilir.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Evlilik teklifi et", style=discord.ButtonStyle.success, emoji="💍")
    async def evlilik_teklifi_et(self, interaction: discord.Interaction, button: discord.ui.Button):
        if evli_mi(interaction.guild_id, self.teklif_eden.id):
            return await interaction.response.send_message(
                "💍 Zaten evlisin! Yeni bir teklif için önce boşanman gerekiyor.", ephemeral=True
            )
        uygun_adaylar = [
            uye for uye in self.teklif_alabilecekler
            if uye.id != self.teklif_eden.id and not uye.bot
            and not kayitsiz_rolu_var(uye)
            and not evli_mi(interaction.guild_id, uye.id)
        ]
        if not uygun_adaylar:
            return await interaction.response.send_message(
                "💔 Bu shipte teklif gönderebileceğin uygun bir kişi yok. Kendinle evlenemezsin ve evli/bot üyelere teklif gönderemezsin.",
                ephemeral=True,
            )

        hedef = uygun_adaylar[0]
        teklif_embed = discord.Embed(
            title="💍 BİR EVLİLİK TEKLİFİN VAR! 💍",
            description=(
                f"❤️ {self.teklif_eden.mention}, sana kalbini açıyor ve hayatının geri kalanını seninle paylaşmak istiyor!\n\n"
                "Birlikte güzel anılar biriktirmeye, birbirinize destek olmaya ve bu hikâyeyi sonsuza kadar sürdürmeye ne dersin?\n\n"
                f"**{self.teklif_eden.mention} ile evlenmeyi kabul ediyor musun?** 💖\n\n"
                "💍 **KABUL ET** — Yeni bir hikâyenin ilk sayfasını açın.\n"
                "💔 **REDDET** — Teklifi nazikçe geri çevir.\n\n"
                "*⏳ Kararını vermek için 2 dakikan var.*"
            ),
            color=discord.Color.from_rgb(255, 105, 180),
        )
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(
            content=hedef.mention,
            embed=teklif_embed,
            view=EvlilikTeklifiView(self.teklif_eden, hedef),
        )


async def ship_sonuc_gonder(ctx, member1: discord.Member, member2: discord.Member, baslik="💘 Ship Ölçer", minimum_yuzde=1):
    # Kendi kendine ship atmak serbesttir; evlilik teklifi yalnızca başka bir üyeye gönderilebilir.
    yuzde = random.randint(minimum_yuzde, 100)
    embed = discord.Embed(
        title=baslik,
        description=f"{member1.mention}  💗  {member2.mention}\n\n**Aşk uyumu: %{yuzde}**\n{ship_yorumu(yuzde)}",
        color=discord.Color.from_rgb(255, 105, 180),
    )
    view = None
    if yuzde > 90:
        # Normal .ship: komutu kullanan kişi ship eşine teklif edebilir.
        if ctx.author.id == member1.id and member2.id != ctx.author.id and not member2.bot:
            view = ShipEvlilikTeklifiView(ctx.author, [member2])
        elif ctx.author.id == member2.id and member1.id != ctx.author.id and not member1.bot:
            view = ShipEvlilikTeklifiView(ctx.author, [member1])
        # Günün çifti komutunu kullanan kişi çiftte değilse, çiftteki üyelerden birini hedef seçebilir.
        elif ctx.author.id not in (member1.id, member2.id):
            uygun = [m for m in (member1, member2) if not m.bot]
            if uygun:
                view = ShipEvlilikTeklifiView(ctx.author, uygun)
    try:
        kart = await ship_kart_olustur(member1, member2, yuzde)
        await ctx.send(content=f"💘 {member1.mention} ❤️ {member2.mention}", embed=embed, file=discord.File(kart, filename="ship-karti.png"), view=view)
    except Exception as exc:
        print(f"Ship kartı oluşturulamadı: {exc}")
        await ctx.send(content=f"💘 {member1.mention} ❤️ {member2.mention}", embed=embed, view=view)


@bot.command(name="ship", aliases=["aşkölçer", "askolcer"])
@commands.guild_only()
async def ship(ctx, member: discord.Member = None):
    """.ship: Kayıtsız rolü olmayan üyeleri shipler; .ship @üye seçilen kişiyle eşleştirir."""
    if kayitsiz_rolu_var(ctx.author):
        return await ctx.send("🔒 **Kayıtsız** rolüne sahip üyeler ship sistemini kullanamaz. Önce kaydını tamamlamalısın.")
    if member is not None:
        if kayitsiz_rolu_var(member):
            return await ctx.send(f"🔒 {member.mention} **Kayıtsız** rolüne sahip olduğu için ship yapılamaz.")
        await ship_sonuc_gonder(ctx, ctx.author, member)
        return
    adaylar = [m for m in ctx.guild.members if not m.bot and m.id != ctx.author.id and not kayitsiz_rolu_var(m)]
    if not adaylar:
        return await ctx.send("💔 Seni shipleyebileceğim başka bir gerçek üye bulamadım.")
    member2 = random.choice(adaylar)
    await ship_sonuc_gonder(ctx, ctx.author, member2, "💘 Rastgele Ship")


@bot.command(name="shipgununçifti", aliases=["shipgununcifti", "gununcifti"])
@commands.guild_only()
async def shipgununcifti(ctx):
    """Her gün sunucu başına aynı rastgele çifti ve görsel kartı seçer."""
    adaylar = sorted(
        (m for m in ctx.guild.members if not m.bot and not kayitsiz_rolu_var(m)),
        key=lambda m: m.id,
    )
    if len(adaylar) < 2:
        return await ctx.send("💔 Günün çiftini seçmek için **Kayıtsız** rolü olmayan en az iki gerçek üye olmalı.")
    bugun = datetime.now(timezone.utc).date().isoformat()
    rng = random.Random(f"ship-gunun-cifti:{ctx.guild.id}:{bugun}")
    member1, member2 = rng.sample(adaylar, 2)
    await ship_sonuc_gonder(ctx, member1, member2, f"💞 Günün Çifti · {bugun}", minimum_yuzde=90)


# ---------------- EVLİLİK SİSTEMİ ----------------
EVLILIK_DOSYASI = "evlilikler.json"


def evlilikleri_yukle():
    try:
        with open(EVLILIK_DOSYASI, "r", encoding="utf-8") as dosya:
            data = json.load(dosya)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def evlilikleri_kaydet():
    try:
        with open(EVLILIK_DOSYASI, "w", encoding="utf-8") as dosya:
            json.dump(EVLILIKLER, dosya, ensure_ascii=False, indent=2)
    except OSError as exc:
        print(f"Evlilik verileri kaydedilemedi: {exc}")


EVLILIKLER = evlilikleri_yukle()


def evlilik_kaydi(guild_id: int, user_id: int):
    return EVLILIKLER.get(str(guild_id), {}).get(str(user_id))


def evli_mi(guild_id: int, user_id: int) -> bool:
    return evlilik_kaydi(guild_id, user_id) is not None


def evlilik_kur(guild_id: int, user1_id: int, user2_id: int):
    guild_key = str(guild_id)
    EVLILIKLER.setdefault(guild_key, {})
    tarih = datetime.now(timezone.utc).isoformat()
    EVLILIKLER[guild_key][str(user1_id)] = {"spouse_id": user2_id, "since": tarih}
    EVLILIKLER[guild_key][str(user2_id)] = {"spouse_id": user1_id, "since": tarih}
    evlilikleri_kaydet()


def evlilik_bitir(guild_id: int, user1_id: int, user2_id: int):
    guild_data = EVLILIKLER.get(str(guild_id), {})
    guild_data.pop(str(user1_id), None)
    guild_data.pop(str(user2_id), None)
    if not guild_data:
        EVLILIKLER.pop(str(guild_id), None)
    evlilikleri_kaydet()


class EvlilikTeklifiView(discord.ui.View):
    def __init__(self, teklif_eden: discord.Member, teklif_alan: discord.Member):
        super().__init__(timeout=120)
        self.teklif_eden = teklif_eden
        self.teklif_alan = teklif_alan
        self.sonuclandi = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.teklif_alan.id:
            await interaction.response.send_message(
                f"💌 Bu teklifi yalnızca {self.teklif_alan.mention} yanıtlayabilir.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Kabul et", style=discord.ButtonStyle.success, emoji="💍")
    async def kabul_et(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.sonuclandi:
            return await interaction.response.send_message("Bu teklif zaten yanıtlandı.", ephemeral=True)
        guild_id = interaction.guild_id
        if evli_mi(guild_id, self.teklif_eden.id) or evli_mi(guild_id, self.teklif_alan.id):
            self.sonuclandi = True
            for item in self.children:
                item.disabled = True
            return await interaction.response.edit_message(
                content="💔 Teklif yanıtlanamadı; ikinizden biri artık başka biriyle evli.",
                embed=None, view=self,
            )
        self.sonuclandi = True
        evlilik_kur(guild_id, self.teklif_eden.id, self.teklif_alan.id)
        for item in self.children:
            item.disabled = True
        embed = discord.Embed(
            title="💍 Yeni Bir Evlilik!",
            description=f"{self.teklif_eden.mention} ve {self.teklif_alan.mention} artık evli! ❤️\n\nMutluluklar dileriz!",
            color=discord.Color.from_rgb(255, 105, 180),
        )
        await interaction.response.edit_message(content=None, embed=embed, view=self)

    @discord.ui.button(label="Reddet", style=discord.ButtonStyle.danger, emoji="💔")
    async def reddet(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.sonuclandi:
            return await interaction.response.send_message("Bu teklif zaten yanıtlandı.", ephemeral=True)
        self.sonuclandi = True
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"💔 {self.teklif_alan.mention}, {self.teklif_eden.mention} adlı kişinin evlilik teklifini reddetti.",
            embed=None, view=self,
        )

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        self.sonuclandi = True


@bot.command(name="evlen")
@commands.guild_only()
async def evlen(ctx, member: discord.Member):
    if member.id == ctx.author.id:
        return await ctx.send("💍 Kendinle evlenemezsin; bir başkasını etiketle!")
    if member.bot:
        return await ctx.send("🤖 Botlarla evlilik yapılamaz.")
    if evli_mi(ctx.guild.id, ctx.author.id):
        kayit = evlilik_kaydi(ctx.guild.id, ctx.author.id)
        return await ctx.send(f"💍 Zaten evlisin! Eşin: <@{kayit['spouse_id']}>. Yeni teklif için önce `{PREFIX}boşan` kullan.")
    if evli_mi(ctx.guild.id, member.id):
        return await ctx.send(f"💔 {member.mention} zaten evli olduğu için teklif gönderemezsin.")
    embed = discord.Embed(
        title="💍 BİR EVLİLİK TEKLİFİN VAR! 💍",
        description=(
            f"❤️ {ctx.author.mention}, sana kalbini açıyor ve hayatının geri kalanını seninle paylaşmak istiyor!\n\n"
            "Birlikte güzel anılar biriktirmeye, birbirinize destek olmaya ve bu hikâyeyi sonsuza kadar sürdürmeye ne dersin?\n\n"
            f"**{ctx.author.mention} ile evlenmeyi kabul ediyor musun?** 💖\n\n"
            "💍 **KABUL ET** — Yeni bir hikâyenin ilk sayfasını açın.\n"
            "💔 **REDDET** — Teklifi nazikçe geri çevir.\n\n"
            "*⏳ Kararını vermek için çok uzun bekleme… Bu teklifin bir süresi var!*"
        ),
        color=discord.Color.from_rgb(255, 105, 180),
    )
    await ctx.send(content=member.mention, embed=embed, view=EvlilikTeklifiView(ctx.author, member))


class BosanmaOnayView(discord.ui.View):
    def __init__(self, uye: discord.Member, es_id: int):
        super().__init__(timeout=60)
        self.uye = uye
        self.es_id = es_id
        self.sonuclandi = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.uye.id:
            await interaction.response.send_message(
                f"Bu kararı yalnızca {self.uye.mention} verebilir.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Evet, boşanmak istiyorum", style=discord.ButtonStyle.danger, emoji="💔")
    async def evet_bosan(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.sonuclandi:
            return await interaction.response.send_message("Bu karar zaten yanıtlandı.", ephemeral=True)
        kayit = evlilik_kaydi(interaction.guild_id, self.uye.id)
        if not kayit or int(kayit.get("spouse_id", 0)) != self.es_id:
            self.sonuclandi = True
            for item in self.children:
                item.disabled = True
            return await interaction.response.edit_message(
                content="💔 Evlilik kaydı artık bulunamadığı için işlem yapılmadı.", embed=None, view=self
            )
        evlilik_bitir(interaction.guild_id, self.uye.id, self.es_id)
        self.sonuclandi = True
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=(
                f"💔 **BOŞANMA GERÇEKLEŞTİ** 💔\n\n"
                f"{self.uye.mention} ve <@{self.es_id}> artık evli değil.\n\n"
                "Bazen aynı hikâyede yollar ayrılabilir… Umarız ikiniz için de bundan sonrası güzel olur. ❤️‍🩹"
            ), embed=None, view=self
        )

    @discord.ui.button(label="Hayır, vazgeçtim", style=discord.ButtonStyle.secondary, emoji="❤️")
    async def hayir_vazgec(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.sonuclandi:
            return await interaction.response.send_message("Bu karar zaten yanıtlandı.", ephemeral=True)
        self.sonuclandi = True
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"❤️ {self.uye.mention}, boşanma talebinden vazgeçti. Evliliğiniz devam ediyor! 💍",
            embed=None, view=self
        )

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        self.sonuclandi = True


@bot.command(name="boşan", aliases=["bosan"])
@commands.guild_only()
async def bosan(ctx):
    kayit = evlilik_kaydi(ctx.guild.id, ctx.author.id)
    if not kayit:
        return await ctx.send("💔 Şu anda evli görünmüyorsun.")
    es_id = int(kayit["spouse_id"])
    embed = discord.Embed(
        title="💔 BOŞANMA TALEBİ 💔",
        description=(
            "Bazen aynı hikâyede yollar ayrılabilir…\n\n"
            f"**<@{es_id}> ile olan evliliğini sonlandırmak istediğine emin misin?**\n\n"
            "Bu kararı verdiğinde evliliğiniz sona erecek ve artık birbirinizin eşi olmayacaksınız.\n\n"
            "💔 **EVET, BOŞANMAK İSTİYORUM** — Bu evliliği sonlandır.\n"
            "❤️ **HAYIR, VAZGEÇTİM** — Evliliğine devam et.\n\n"
            "*⚠️ Bu karar senin elinde. Son kararını vermeden önce bir kez daha düşün.*"
        ),
        color=discord.Color.from_rgb(220, 70, 90),
    )
    await ctx.send(embed=embed, view=BosanmaOnayView(ctx.author, es_id))


@bot.command(name="evlilik")
@commands.guild_only()
async def evlilik(ctx, member: discord.Member = None):
    member = member or ctx.author
    kayit = evlilik_kaydi(ctx.guild.id, member.id)
    embed = discord.Embed(title=f"💞 {member.display_name} — AŞKIN HİKÂYESİ 💞", color=discord.Color.from_rgb(255, 105, 180))
    embed.set_thumbnail(url=member.display_avatar.url)
    if not kayit:
        embed.description = f"💔 {member.mention} şu anda evli değil.\n\n*Belki de aşk hikâyesinin ilk sayfası henüz yazılmadı…* ❤️"
    else:
        es_id = int(kayit["spouse_id"])
        tarih_raw = kayit.get("since")
        try:
            tarih = datetime.fromisoformat(tarih_raw)
            evlilik_tarihi = discord.utils.format_dt(tarih, 'D')
            evlilik_suresi = discord.utils.format_dt(tarih, 'R')
            embed.description = (
                f"💍 **Eşler:** {member.mention} ❤️ <@{es_id}>\n"
                f"📅 **Evlilik tarihi:** {evlilik_tarihi}\n"
                f"⏳ **Birlikte geçen süre:** {evlilik_suresi}\n\n"
                "İki kalp, tek bir hikâye… ❤️\n\n"
                "Birlikte geçirdiğiniz her gün, bu hikâyeye yeni bir anı ekliyor. Dileriz sevginiz daim, mutluluğunuz sonsuz olsun! 🥂💖\n\n"
                "*“Gerçek aşk, her gün yeniden birbirini seçmektir.”* 💍"
            )
        except (TypeError, ValueError):
            embed.description = f"💍 **Eşler:** {member.mention} ❤️ <@{es_id}>\n\nİki kalp, tek bir hikâye… ❤️"
    await ctx.send(embed=embed)


# ---------------- SPOTIFY ----------------
def spotify_font(size, bold=False):
    """Windows'ta Arial kullanır; bulunamazsa Pillow varsayılan fontuna döner."""
    candidates = []
    if os.name == "nt":
        candidates.append(r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf")
    candidates.extend(["arialbd.ttf" if bold else "arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"])
    for font_path in candidates:
        try:
            return ImageFont.truetype(font_path, size)
        except (OSError, IOError):
            pass
    return ImageFont.load_default()


async def spotify_kart_olustur(activity):
    """Spotify etkinliğinden PNG kart üretir."""
    width, height = 1200, 500
    image = Image.new("RGB", (width, height), (16, 18, 20))
    draw = ImageDraw.Draw(image)

    # Arka plan ve kart yüzeyi
    draw.rounded_rectangle((18, 18, width - 18, height - 18), radius=30, fill=(24, 27, 30))
    draw.rounded_rectangle((42, 42, 1158, 458), radius=24, fill=(29, 33, 36))

    # Albüm kapağını indir; indirme başarısız olursa sade kapak kullan.
    cover = None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(activity.album_cover_url, timeout=aiohttp.ClientTimeout(total=12)) as response:
                if response.status == 200:
                    cover_bytes = await response.read()
                    cover = Image.open(io.BytesIO(cover_bytes)).convert("RGB")
    except Exception as exc:
        print(f"Spotify albüm kapağı indirilemedi: {exc}")

    cover_size = 330
    cover_x, cover_y = 790, 85
    if cover is not None:
        cover = cover.resize((cover_size, cover_size), Image.Resampling.LANCZOS)
        image.paste(cover, (cover_x, cover_y))
        # Albüm kapağının çevresine hafif bir çerçeve
        draw.rounded_rectangle((cover_x - 2, cover_y - 2, cover_x + cover_size + 2, cover_y + cover_size + 2), radius=8, outline=(70, 75, 78), width=2)
    else:
        draw.rounded_rectangle((cover_x, cover_y, cover_x + cover_size, cover_y + cover_size), radius=12, fill=(35, 90, 60))
        draw.text((cover_x + 75, cover_y + 135), "SPOTIFY", font=spotify_font(36, True), fill=(255, 255, 255))

    # Spotify başlığı
    green = (30, 215, 96)
    draw.ellipse((78, 75, 120, 117), fill=green)
    # Üç basit ses dalgası çizgisi
    for offset, width_line in [(0, 25), (8, 20), (16, 14)]:
        draw.arc((85, 82 + offset, 111, 98 + offset), start=200, end=340, fill=(18, 28, 22), width=3)
    draw.text((135, 80), "Spotify", font=spotify_font(30, True), fill=(245, 247, 246))
    draw.text((78, 155), "ŞİMDİ ÇALIYOR", font=spotify_font(18, True), fill=green)

    title = str(activity.title or "Bilinmeyen şarkı")
    artist = str(activity.artist or "Bilinmeyen sanatçı")
    album = str(activity.album or "Albüm bilgisi yok")

    def fit_text(text, font, max_width):
        while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
            text = text[:-2].rstrip() + "…"
        return text

    title_font = spotify_font(40, True)
    artist_font = spotify_font(27)
    album_font = spotify_font(20)
    text_width = 660
    draw.text((78, 200), fit_text(title, title_font, text_width), font=title_font, fill=(255, 255, 255))
    draw.text((80, 260), fit_text(artist, artist_font, text_width), font=artist_font, fill=(208, 213, 215))
    draw.text((80, 305), fit_text(album, album_font, text_width), font=album_font, fill=(150, 158, 162))

    # İlerleme çubuğu
    bar_x, bar_y, bar_w = 80, 385, 640
    draw.rounded_rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + 8), radius=4, fill=(75, 81, 84))
    elapsed = 0.0
    duration_seconds = 0.0
    try:
        duration_seconds = activity.duration.total_seconds()
        if activity.start:
            start = activity.start
            now = datetime.now(timezone.utc)
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            elapsed = max(0.0, min((now - start).total_seconds(), duration_seconds))
    except Exception:
        pass
    if duration_seconds > 0:
        progress_w = int(bar_w * min(1.0, elapsed / duration_seconds))
        if progress_w > 0:
            draw.rounded_rectangle((bar_x, bar_y, bar_x + progress_w, bar_y + 8), radius=4, fill=green)

    def time_text(seconds):
        seconds = max(0, int(seconds))
        return f"{seconds // 60}:{seconds % 60:02d}"

    draw.text((bar_x, 405), time_text(elapsed), font=spotify_font(17), fill=(190, 196, 199))
    total_text = time_text(duration_seconds) if duration_seconds else "--:--"
    total_box = draw.textbbox((0, 0), total_text, font=spotify_font(17))
    draw.text((bar_x + bar_w - (total_box[2] - total_box[0]), 405), total_text, font=spotify_font(17), fill=(190, 196, 199))
    draw.text((80, 435), "Discord Spotify kartı", font=spotify_font(14), fill=(110, 119, 123))

    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    output.seek(0)
    return output


@bot.command(name="sp", aliases=["spo", "spotify"])
async def spotify(ctx, member: discord.Member = None):
    """Kendinin veya belirtilen üyenin Discord Spotify etkinliğini görsel kart olarak gönderir."""
    member = member or ctx.author
    activity = next((a for a in getattr(member, "activities", []) if isinstance(a, discord.Spotify)), None)
    if activity is None:
        await ctx.send("🎧 Spotify etkinliği görünmüyor. Spotify hesabını Discord'a bağla ve dinleme etkinliğinin görünür olduğundan emin ol.")
        return
    try:
        image_bytes = await spotify_kart_olustur(activity)
        await ctx.send(file=discord.File(image_bytes, filename="spotify-kart.png"))
    except Exception as exc:
        print(f"Spotify kartı oluşturulamadı: {exc}")
        await ctx.send("❌ Spotify kartı oluşturulamadı. Konsoldaki hata mesajını kontrol et.")


@bot.command(name="adam")
async def adam(ctx):
    """.adam komutu ile belirtilen görseli paylaşır."""
    adam_gorseli = "https://cdn.discordapp.com/attachments/1541931901277966558/1562569679204122654/IMG_3003.jpg?ex=6ada77ea&is=6ad9266a&hm=e3110185fec8b5f147288c4b0430c0584a829e2c1bd04342daa47a1861b024d3&"
    embed = discord.Embed()
    embed.set_image(url=adam_gorseli)
    await ctx.send(embed=embed)




@bot.command(name="dgko")
@commands.guild_only()
@commands.has_permissions(manage_roles=True)
async def dgko(ctx, member: discord.Member):
    """Üyeye DGKO rolünü verir ve Türkiye saatiyle 00.00'da kaldırır."""
    role = ctx.guild.get_role(DGKO_ROL_ID)
    if role is None:
        await ctx.send(f"❌ Bu sunucuda `{DGKO_ROL_ID}` ID'li rol bulunamadı.")
        return
    if not ctx.guild.me.guild_permissions.manage_roles:
        await ctx.send("❌ Botta **Rolleri Yönet** izni yok.")
        return
    if role >= ctx.guild.me.top_role:
        await ctx.send("❌ Bu rol botun en yüksek rolünün altında olmalı.")
        return
    if member == ctx.guild.me:
        await ctx.send("❌ Bu rolü bota veremem.")
        return

    # Üyede zaten varsa gece yarısı kaldırmamak için geçici kayıt oluşturma.
    if role in member.roles:
        await ctx.send(f"ℹ️ {member.mention} bu role zaten sahip; mevcut rolüne dokunmadım.")
        return

    try:
        await member.add_roles(role, reason=f"{ctx.author} tarafından .dgko komutuyla geçici rol verildi")
    except discord.Forbidden:
        await ctx.send("❌ Rol verilemedi. Botun **Rolleri Yönet** iznini ve rol sıralamasını kontrol et.")
        return
    except discord.HTTPException:
        await ctx.send("❌ Discord rolü verirken hata oluştu. Biraz sonra tekrar dene.")
        return

    simdi = datetime.now(TURKIYE_SAATI)
    gece_yarisi = (simdi + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    kayitlar = dgko_kayitlarini_oku()
    kayitlar.append({
        "guild_id": ctx.guild.id,
        "member_id": member.id,
        "role_id": role.id,
        "kaldirma_zamani": gece_yarisi.isoformat(),
    })
    dgko_kayitlarini_yaz(kayitlar)
    await ctx.send(f"✅ {member.mention} kişisine {role.mention} rolünü verdim. Rol Türkiye saatiyle bu gece **00.00'da** geri alınacak.")

@bot.command(name="admin")
async def admin(ctx):
    """.admin komutunda belirtilen üyeyi etiketleyen mesajı gönderir."""
    await ctx.send("<@1130431011650547712> senin gibi adminin 🤬")


@bot.command(name="amparator")
async def amparator(ctx):
    """.amparator komutunda belirtilen üyeyi etiketler."""
    await ctx.send("<@988545310085242980>")


@bot.command(name="meshuroç", aliases=["meshuroc"])
async def meshuroc(ctx):
    """.meshuroç komutunda belirtilen üyeyi etiketler."""
    await ctx.send("<@703979673046220841>")


# ---------------- BAŞLAT ----------------
if not TOKEN:
    raise SystemExit("TOKEN bulunamadı. .env dosyasında TOKEN=... satırının olduğundan emin ol.")

bot.run(TOKEN)
