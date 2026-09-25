<?xml version="1.0" encoding="UTF-8"?>
<!-- ==================================================================
     mei2rdf.xsl  -  MEI (MerMEId/DCM profile) -> RDF/Turtle
     CM3070 feature prototype: the "Transform" pillar.
     XSLT 3.0, run with Saxon-HE. Emits one Turtle document per MEI work.
     Reuses Music Ontology, FRBR core, Dublin Core, FOAF; a small
     project vocabulary (cnw:) covers catalogue-specific properties.
     ================================================================== -->
<xsl:stylesheet version="3.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:f="urn:cnw:functions"
    xpath-default-namespace="http://www.music-encoding.org/ns/mei"
    exclude-result-prefixes="xs f">

	<xsl:output method="text" encoding="UTF-8"/>
	<xsl:strip-space elements="*"/>

	<!-- Base IRIs -->
	<xsl:variable name="base"  select="'https://cnw-ld.org/'"/>
	<xsl:variable name="onto"  select="'https://cnw-ld.org/ontology#'"/>

	<!-- ============ helper functions ============ -->

	<!-- Escape a string for use inside a Turtle quoted literal -->
	<xsl:function name="f:esc" as="xs:string">
		<xsl:param name="s" as="xs:string"/>
		<xsl:variable name="a" select="replace($s, '\\', '\\\\')"/>
		<xsl:variable name="b" select="replace($a, '&quot;', '\\&quot;')"/>
		<xsl:variable name="c" select="replace($b, '&#10;', '\\n')"/>
		<xsl:variable name="d" select="replace($c, '&#13;', '\\r')"/>
		<xsl:value-of select="replace($d, '&#9;', '\\t')"/>
	</xsl:function>

	<!-- Plain language-tagged or plain literal -->
	<xsl:function name="f:lit" as="xs:string">
		<xsl:param name="s" as="xs:string?"/>
		<xsl:param name="lang" as="xs:string?"/>
		<xsl:variable name="txt" select="normalize-space(string($s))"/>
		<xsl:choose>
			<xsl:when test="$lang != ''">
				<xsl:value-of select="concat('&quot;', f:esc($txt), '&quot;@', $lang)"/>
			</xsl:when>
			<xsl:otherwise>
				<xsl:value-of select="concat('&quot;', f:esc($txt), '&quot;')"/>
			</xsl:otherwise>
		</xsl:choose>
	</xsl:function>

	<!-- Slug: lowercase, non-alphanumeric -> underscore -->
	<xsl:function name="f:slug" as="xs:string">
		<xsl:param name="s" as="xs:string"/>
		<xsl:variable name="low" select="lower-case(normalize-space($s))"/>
		<xsl:value-of select="replace(replace($low, '[^a-z0-9]+', '_'), '^_|_$', '')"/>
	</xsl:function>

	<!-- Catalogue number reduced to IRI-safe characters. The verbatim value is
     still preserved as the cnw:cnwNumber literal (rule R2). -->
	<xsl:function name="f:idPart" as="xs:string">
		<xsl:param name="s" as="xs:string"/>
		<xsl:value-of select="replace(replace(normalize-space($s), '[^A-Za-z0-9]+', '-'), '^-|-$', '')"/>
	</xsl:function>

	<!-- Catalogue codes treated as primary work identifiers, in precedence order.
     Each DCM catalogue labels its own numbering (CNW 446, NWGW 483, HartW 590,
     SchW 401 in the full corpus), so the code is read from the data rather than
     assumed. -->
	<xsl:variable name="f:catalogueCodes" as="xs:string+"
				  select="('CNW', 'NWGW', 'HartW', 'SchW')"/>

	<!-- The work's primary catalogue identifier element, if it has one. -->
	<xsl:function name="f:catId" as="element()?">
		<xsl:param name="work" as="element()"/>
		<xsl:sequence select="($work/identifier[normalize-space(@label) = $f:catalogueCodes]
                           [normalize-space(.) != ''])[1]"/>
	</xsl:function>

	<!-- Work IRI: catalogue code plus number, e.g. .../work/NWGW12. The code forms
     part of the IRI because numbering restarts in every catalogue, so Gade 12
     and Nielsen 12 are different works. The title-slug fallback now also carries
     the record's own xml:id, because across the four-catalogue corpus the bare
     slug collapsed 116 distinct works onto shared IRIs. -->
	<xsl:function name="f:workIri" as="xs:string">
		<xsl:param name="work" as="element()"/>
		<xsl:variable name="id" select="f:catId($work)"/>
		<xsl:choose>
			<xsl:when test="exists($id)">
				<xsl:value-of select="concat('https://cnw-ld.org/work/',
                                         f:idPart(normalize-space($id/@label)),
                                         f:idPart(normalize-space($id)))"/>
			</xsl:when>
			<xsl:otherwise>
				<xsl:value-of select="concat('https://cnw-ld.org/work/',
                                         f:slug(string($work/title[1])), '_',
                                         substring(string($work/@xml:id), 1, 12))"/>
			</xsl:otherwise>
		</xsl:choose>
	</xsl:function>

	<!-- ============ main ============ -->
	<xsl:template match="/">
		<xsl:variable name="work" select="(//work)[1]"/>
		<xsl:variable name="wIri" select="f:workIri($work)"/>
		<xsl:variable name="L" as="xs:string*">

			<!-- prefixes -->
			<xsl:sequence select="'@prefix ex:      &lt;https://cnw-ld.org/&gt; .'"/>
			<xsl:sequence select="'@prefix cnw:     &lt;https://cnw-ld.org/ontology#&gt; .'"/>
			<xsl:sequence select="'@prefix frbr:    &lt;http://purl.org/vocab/frbr/core#&gt; .'"/>
			<xsl:sequence select="'@prefix mo:      &lt;http://purl.org/ontology/mo/&gt; .'"/>
			<xsl:sequence select="'@prefix dcterms: &lt;http://purl.org/dc/terms/&gt; .'"/>
			<xsl:sequence select="'@prefix foaf:    &lt;http://xmlns.com/foaf/0.1/&gt; .'"/>
			<xsl:sequence select="'@prefix owl:     &lt;http://www.w3.org/2002/07/owl#&gt; .'"/>
			<xsl:sequence select="'@prefix rdf:     &lt;http://www.w3.org/1999/02/22-rdf-syntax-ns#&gt; .'"/>
			<xsl:sequence select="'@prefix rdfs:    &lt;http://www.w3.org/2000/01/rdf-schema#&gt; .'"/>
			<xsl:sequence select="'@prefix xsd:     &lt;http://www.w3.org/2001/XMLSchema#&gt; .'"/>
			<xsl:sequence select="''"/>

			<!-- ===== Work node ===== -->
			<xsl:sequence select="concat('&lt;', $wIri, '&gt;')"/>
			<xsl:sequence select="'    a frbr:Work, mo:MusicalWork ;'"/>

			<!-- titles: untyped or main titles are the work title. Where a record has none (four works in the full catalogue), the typed titles are promoted so no work is left without one. Remaining variants become alternatives. -->
			<xsl:variable name="mainTitles" select="$work/title[not(@type) or @type='main']"/>
			<xsl:variable name="titleNodes" select="if (exists($mainTitles)) then $mainTitles else $work/title"/>
			<xsl:for-each select="$titleNodes">
				<xsl:sequence select="concat('    dcterms:title ', f:lit(string(.), string(@xml:lang)), ' ;')"/>
			</xsl:for-each>
			<xsl:for-each select="$work/title except $titleNodes">
				<xsl:sequence select="concat('    dcterms:alternative ', f:lit(string(.), string(@xml:lang)), ' ;')"/>
			</xsl:for-each>

			<!-- catalogue numbers: convenience flat properties + structured nodes -->
			<xsl:for-each select="$work/identifier[normalize-space(.) != '']">
				<xsl:sequence select="concat('    dcterms:identifier ', f:lit(concat(@label,' ',normalize-space(.)), ''), ' ;')"/>
			</xsl:for-each>
			<xsl:variable name="catId" select="f:catId($work)"/>
			<xsl:if test="exists($catId)">
				<!-- cnw:cnwNumber keeps its name for continuity with the single-catalogue
         build, but now holds the number of whichever catalogue the record
         belongs to. cnw:catalogueCode says which one that is. -->
				<xsl:sequence select="concat('    cnw:cnwNumber ', f:lit(normalize-space($catId),''), ' ;')"/>
				<xsl:sequence select="concat('    cnw:catalogueCode ', f:lit(normalize-space($catId/@label),''), ' ;')"/>
			</xsl:if>
			<xsl:variable name="opus" select="normalize-space($work/identifier[@label='Opus'][1])"/>
			<xsl:if test="$opus != ''">
				<!-- normalise irregular spacing in opus, e.g. '10. 1' -> '10.1' -->
				<xsl:sequence select="concat('    cnw:opus ', f:lit(replace($opus,'\s+',''),''), ' ;')"/>
			</xsl:if>
			<xsl:variable name="fs" select="normalize-space($work/identifier[@label='FS'][1])"/>
			<xsl:if test="$fs != ''">
				<xsl:sequence select="concat('    cnw:fsNumber ', f:lit($fs,''), ' ;')"/>
			</xsl:if>

			<!-- creators / contributors -->
			<xsl:for-each select="$work/contributor/persName[@role='composer']">
				<xsl:sequence select="concat('    dcterms:creator ', f:agentRef(.), ' ;')"/>
			</xsl:for-each>
			<xsl:for-each select="$work/contributor/persName[@role='author']">
				<xsl:sequence select="concat('    cnw:textAuthor ', f:agentRef(.), ' ;')"/>
			</xsl:for-each>

			<!-- Arrangements. In the Hartmann catalogue the B series are arrangements of
				folk songs and other composers' material, so Hartmann is encoded as the
				arranger and there is no composer at all. Mapping only composer and author
				silently dropped his involvement from 73 records. -->
			<xsl:for-each select="$work/contributor/persName[@role='arranger']">
				<xsl:sequence select="concat('    cnw:arranger ', f:agentRef(.), ' ;')"/>
			</xsl:for-each>
			
			<!-- creation date -->
			<xsl:variable name="cd" select="$work/creation/date[1]"/>
			<xsl:if test="$cd">
				<xsl:if test="normalize-space($cd) != ''">
					<xsl:sequence select="concat('    dcterms:created ', f:lit(string($cd),''), ' ;')"/>
				</xsl:if>
				<xsl:if test="$cd/@notbefore">
					<xsl:sequence select="concat('    cnw:dateNotBefore &quot;', $cd/@notbefore, '&quot;^^xsd:gYear ;')"/>
				</xsl:if>
				<xsl:if test="$cd/@notafter">
					<xsl:sequence select="concat('    cnw:dateNotAfter &quot;', $cd/@notafter, '&quot;^^xsd:gYear ;')"/>
				</xsl:if>
			</xsl:if>

			<!-- languages -->
			<xsl:for-each select="$work/langUsage/language">
				<xsl:sequence select="concat('    dcterms:language ', f:lit(string(.),''), ' ;')"/>
			</xsl:for-each>

			<!-- genre / classification -->
			<xsl:for-each select="$work/classification//term[normalize-space(.) != '']">
				<xsl:sequence select="concat('    dcterms:subject ', f:lit(string(.),''), ' ;')"/>
			</xsl:for-each>

			<!-- relations -->
			<xsl:for-each select="$work/relationList/relation[@rel='isPartOf']">
				<xsl:sequence select="concat('    dcterms:isPartOf &lt;https://cnw-ld.org/collection/', f:slug(replace(string(@target),'\.xml$','')), '&gt; ;')"/>
			</xsl:for-each>

			<!-- editorial annotations -->
			<xsl:for-each select="$work//annot[normalize-space(.) != '']">
				<xsl:variable name="atype" select="if (@type!='') then string(@type) else 'note'"/>
				<xsl:choose>
					<xsl:when test="$atype='source_description'">
						<xsl:sequence select="concat('    cnw:sourceDescription ', f:lit(string(.),''), ' ;')"/>
					</xsl:when>
					<xsl:otherwise>
						<xsl:sequence select="concat('    cnw:editorialNote ', f:lit(string(.),''), ' ;')"/>
					</xsl:otherwise>
				</xsl:choose>
			</xsl:for-each>
			<!-- manuscript / source locations -->
			<xsl:for-each select="$work//physLoc/repository[normalize-space(.) != '']">
				<xsl:sequence select="concat('    cnw:manuscriptLocation ', f:lit(string(.),''), ' ;')"/>
			</xsl:for-each>

			<!-- expression link -->
			<xsl:sequence select="concat('    frbr:realization &lt;', $wIri, '/expression/1&gt; ;')"/>

			<!-- performance count -->
			<xsl:variable name="perf" select="$work/history//eventList[@type='performances']/event"/>
			<xsl:sequence select="concat('    cnw:performanceCount ', count($perf), ' .')"/>
			<xsl:sequence select="''"/>

			<!-- ===== Expression node ===== -->
			<xsl:variable name="expr" select="($work//expression)[1]"/>
			<xsl:if test="$expr">
				<xsl:sequence select="concat('&lt;', $wIri, '/expression/1&gt;')"/>
				<xsl:sequence select="'    a frbr:Expression ;'"/>
				<xsl:sequence select="concat('    frbr:realizationOf &lt;', $wIri, '&gt; ;')"/>

				<!-- key: first expression that actually carries one, incl. accidental -->
				<xsl:variable name="k" select="($work//key[@pname])[1]"/>
				<xsl:if test="$k">
					<xsl:variable name="acc" select="if ($k/@accid='f') then '-flat' else if ($k/@accid='s') then '-sharp' else ''"/>
					<xsl:variable name="keystr"
					  select="normalize-space(concat(upper-case(string($k/@pname)), $acc, ' ', string($k/@mode)))"/>
					<xsl:if test="$keystr != ''">
						<xsl:sequence select="concat('    cnw:key ', f:lit($keystr,''), ' ;')"/>
					</xsl:if>
				</xsl:if>

				<!-- tempo -->
				<xsl:for-each select="($work//tempo[normalize-space(.) != ''])[1]">
					<xsl:sequence select="concat('    cnw:tempo ', f:lit(string(.),''), ' ;')"/>
				</xsl:for-each>

				<!-- meter: handle both count/unit and @sym (common/cut) encodings -->
				<xsl:variable name="m" select="($work//meter[@count or @sym])[1]"/>
				<xsl:if test="$m">
					<xsl:variable name="meterstr" as="xs:string?">
						<xsl:choose>
							<xsl:when test="$m/@count and $m/@unit">
								<xsl:value-of select="concat($m/@count,'/',$m/@unit)"/>
							</xsl:when>
							<xsl:when test="$m/@sym='common'">4/4</xsl:when>
							<xsl:when test="$m/@sym='cut'">2/2</xsl:when>
							<xsl:when test="$m/@sym">
								<xsl:value-of select="string($m/@sym)"/>
							</xsl:when>
							<xsl:otherwise/>
						</xsl:choose>
					</xsl:variable>
					<xsl:if test="$meterstr != ''">
						<xsl:sequence select="concat('    cnw:meter ', f:lit($meterstr,''), ' ;')"/>
					</xsl:if>
				</xsl:if>

				<!-- scoring / performing forces -->
				<xsl:for-each select="$expr//perfMedium//perfRes[normalize-space(.) != '']">
					<xsl:sequence select="concat('    cnw:performingForce ', f:lit(string(.),''), ' ;')"/>
				</xsl:for-each>

				<!-- incipit text -->
				<xsl:for-each select="$work//incip/incipText/p[normalize-space(.) != '']">
					<xsl:sequence select="concat('    cnw:incipitText ', f:lit(string(.), string(@xml:lang)), ' ;')"/>
				</xsl:for-each>

				<!-- incipit image (hires graphic if present) -->
				<xsl:variable name="g" select="($work//incip/graphic[@targettype='hires'], $work//incip/graphic)[1]"/>
				<xsl:if test="$g/@target">
					<xsl:sequence select="concat('    cnw:incipitImage ', f:lit(tokenize(string($g/@target),'/')[last()],''), ' ;')"/>
				</xsl:if>

				<!-- notated incipit (notation inside the incip element) vs notated
             music anywhere in the record (e.g. a full <music> body). Both
             matter: the latter is what Verovio can render. -->
				<xsl:variable name="incipScore" select="exists($expr//incip//score)"/>
				<xsl:variable name="anyScore" select="exists(//music//score)"/>
				<xsl:sequence select="concat('    cnw:hasNotatedIncipit ', if ($incipScore) then 'true' else 'false', ' ;')"/>
				<xsl:sequence select="concat('    cnw:hasNotatedMusic ', if ($anyScore) then 'true' else 'false', ' .')"/>
				<xsl:sequence select="''"/>
			</xsl:if>

			<!-- ===== Agent nodes (deduplicated) ===== -->
			<xsl:for-each-group select="$work/contributor/persName" group-by="normalize-space(.)">
				<xsl:variable name="p" select="current-group()[1]"/>
				<xsl:sequence select="f:agentRef($p)"/>
				<xsl:sequence select="'    a foaf:Agent ;'"/>
				<xsl:sequence select="concat('    foaf:name ', f:lit(string($p),''),
          (if ($p/@auth='VIAF' and normalize-space($p/@codedval)!='') then ' ;' else ' .'))"/>
				<xsl:if test="$p/@auth='VIAF' and normalize-space($p/@codedval)!=''">
					<xsl:sequence select="concat('    owl:sameAs &lt;http://viaf.org/viaf/', normalize-space($p/@codedval), '&gt; .')"/>
				</xsl:if>
				<xsl:sequence select="''"/>
			</xsl:for-each-group>

		</xsl:variable>

		<xsl:value-of select="string-join($L, '&#10;')"/>
		<xsl:text>&#10;</xsl:text>
	</xsl:template>

	<!-- Agent IRI reference (by VIAF if available, else by name slug) -->
	<xsl:function name="f:agentRef" as="xs:string">
		<xsl:param name="p" as="element()"/>
		<xsl:choose>
			<xsl:when test="$p/@auth='VIAF' and normalize-space($p/@codedval) != ''">
				<xsl:value-of select="concat('&lt;https://cnw-ld.org/agent/viaf/', normalize-space($p/@codedval), '&gt;')"/>
			</xsl:when>
			<xsl:otherwise>
				<xsl:value-of select="concat('&lt;https://cnw-ld.org/agent/', f:slug(string($p)), '&gt;')"/>
			</xsl:otherwise>
		</xsl:choose>
	</xsl:function>

</xsl:stylesheet>
