<xsl:stylesheet version="2.0"
 xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
 xmlns:xs="http://www.w3.org/2001/XMLSchema"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
 xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
 xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
 xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0"
 xmlns:xlink="http://www.w3.org/1999/xlink"
 xmlns:pg="urn:teify:conversion"
 xmlns:tei="http://www.tei-c.org/ns/1.0"
 xmlns="http://www.tei-c.org/ns/1.0"
 exclude-result-prefixes="xs text office table draw svg xlink pg tei">
 <xsl:import href="__UPSTREAM__"/>
 <xsl:output indent="no"/>
 <xsl:template name="teiHeader">
  <teiHeader><fileDesc><titleStmt><title>Pending metadata</title></titleStmt><publicationStmt><p>Conversion</p></publicationStmt><sourceDesc><p>Source document</p></sourceDesc></fileDesc></teiHeader>
 </xsl:template>
 <xsl:template name="source-attributes">
  <xsl:if test="@pg:id"><xsl:attribute name="xml:id" select="@pg:id"/></xsl:if>
  <xsl:if test="@pg:css"><xsl:attribute name="style" select="@pg:css"/></xsl:if>
  <xsl:if test="@text:style-name"><xsl:attribute name="rend" select="@text:style-name"/></xsl:if>
 </xsl:template>
 <xsl:template match="text:p" priority="20">
  <p><xsl:call-template name="source-attributes"/>
   <xsl:if test="@pg:drama"><xsl:attribute name="type" select="concat('drama-',@pg:drama)"/></xsl:if>
   <xsl:if test="@pg:verse='true'"><xsl:attribute name="type">verse-stanza</xsl:attribute></xsl:if>
   <xsl:apply-templates/>
  </p>
 </xsl:template>
 <xsl:template match="text:h" priority="20">
  <xsl:choose>
   <xsl:when test="ancestor::text:note-body or ancestor::table:table or ancestor::draw:text-box or ancestor::text:table-of-content or ancestor::text:alphabetical-index or ancestor::text:user-index">
    <p><xsl:call-template name="source-attributes"/><xsl:apply-templates/></p>
   </xsl:when>
   <xsl:otherwise>
    <HEAD level="{@text:outline-level}">
     <seg type="source-heading"><xsl:call-template name="source-attributes"/>
      <xsl:attribute name="n" select="@pg:original-level"/>
      <xsl:apply-templates/>
     </seg>
    </HEAD>
   </xsl:otherwise>
  </xsl:choose>
 </xsl:template>
 <xsl:template match="text:span" priority="20">
  <hi><xsl:call-template name="source-attributes"/><xsl:apply-templates/></hi>
 </xsl:template>
 <xsl:template match="text:a" priority="20">
  <ref target="{if (@pg:target) then @pg:target else @xlink:href}"><xsl:if test="@pg:css"><xsl:attribute name="style" select="@pg:css"/></xsl:if><xsl:apply-templates/></ref>
 </xsl:template>
 <xsl:template match="text:line-break" priority="20"><lb/></xsl:template>
 <xsl:template match="text:s" priority="20"><xsl:value-of select="string-join(for $i in 1 to (if (@text:c) then xs:integer(@text:c) else 1) return ' ', '')"/></xsl:template>
 <xsl:template match="text:tab" priority="20"><space type="tab" quantity="1" unit="chars"/></xsl:template>
 <xsl:template match="text:soft-page-break" priority="20"><pb/></xsl:template>
 <xsl:template match="text:table-of-content | text:alphabetical-index | text:user-index" priority="20">
  <list type="{if (self::text:table-of-content) then 'contents' else 'index'}"><xsl:for-each select="text:index-body/*"><item><xsl:apply-templates select="."/></item></xsl:for-each></list>
 </xsl:template>
 <xsl:template match="text:index-body | text:index-title" priority="20"><xsl:apply-templates/></xsl:template>
 <xsl:template match="draw:frame | draw:custom-shape | draw:rect | draw:line" priority="20"><figure><xsl:apply-templates/></figure></xsl:template>
 <xsl:template match="draw:image" priority="20"><graphic url="{@xlink:href}"/></xsl:template>
 <xsl:template match="svg:title | svg:desc" priority="20"><figDesc><xsl:apply-templates/></figDesc></xsl:template>
 <xsl:template match="text:reference-ref | text:bookmark-ref" priority="20"><ref target="{if (@pg:target) then @pg:target else concat('#id_',@text:ref-name)}"><xsl:apply-templates/></ref></xsl:template>
 <xsl:template match="text:bookmark | text:bookmark-start | text:reference-mark | text:reference-mark-start | text:alphabetical-index-mark | text:alphabetical-index-mark-start | text:toc-mark | text:toc-mark-start | text:user-index-mark | text:user-index-mark-start" priority="20">
  <anchor type="{local-name()}"><xsl:attribute name="xml:id" select="@pg:anchor"/><xsl:attribute name="n" select="if (@pg:index-metadata) then @pg:index-metadata else @text:name"/></anchor>
 </xsl:template>
 <xsl:template match="text:bookmark-end | text:reference-mark-end | text:alphabetical-index-mark-end | text:toc-mark-end | text:user-index-mark-end" priority="20">
  <xsl:choose><xsl:when test="@pg:target"><ptr type="{local-name()}" target="{@pg:target}"/></xsl:when><xsl:otherwise><anchor type="{local-name()}" n="{@text:id}"/></xsl:otherwise></xsl:choose>
 </xsl:template>
 <!-- A list without items is an ODF layout wrapper, not an empty TEI list. -->
 <xsl:template match="text:list[not(text:list-item)]" priority="20"><xsl:apply-templates/></xsl:template>
 <!-- Upstream flattens heading lists but accidentally discards their headers. -->
 <xsl:template match="text:list[text:list-item/text:h or text:list-header/text:h]" priority="21"><xsl:apply-templates select="text:list-header/* | text:list-item/*"/></xsl:template>
 <xsl:template match="text:list-header" priority="20">
  <xsl:choose><xsl:when test="../text:list-item"><item rend="list-header"><xsl:apply-templates/></item></xsl:when><xsl:otherwise><xsl:apply-templates/></xsl:otherwise></xsl:choose>
 </xsl:template>
 <!-- Retain field display values which the base transform would omit. -->
 <xsl:template match="text:page-number | text:page-count | text:date | text:time | text:author-name | text:file-name | text:variable-set | text:variable-get" priority="20"><xsl:apply-templates/></xsl:template>
 <!-- Preserve source paragraphs, including empty ones, through upstream passes. -->
 <xsl:template match="tei:p[@xml:id]" mode="pass1" priority="20"><xsl:copy><xsl:apply-templates select="@*|node()" mode="pass1"/></xsl:copy></xsl:template>
 <xsl:template match="tei:p[@xml:id]" mode="pass2" priority="20"><xsl:copy><xsl:apply-templates select="@*|node()" mode="pass2"/></xsl:copy></xsl:template>
</xsl:stylesheet>
